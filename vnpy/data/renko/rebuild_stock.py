# encoding: UTF-8

# 股票砖图数据重构器

import os
import copy
import csv
import signal
import traceback

from queue import Queue
from datetime import datetime, timedelta
from time import sleep
from threading import Thread

from vnpy.data.tdx.tdx_stock_data import TdxStockData
from vnpy.data.tdx.tdx_common import FakeStrategy
from vnpy.data.mongo.mongo_data import MongoData
from vnpy.data.renko.config import STOCK_RENKO_DB_NAME, HEIGHT_LIST
from vnpy.app.cta_strategy_pro.cta_renko_bar import CtaRenkoBar
from vnpy.trader.object import TickData, RenkoBarData, Exchange, Color
from vnpy.trader.utility import get_trading_date, get_stock_exchange


class StockRenkoRebuilder(FakeStrategy):

    def __init__(self, setting={}):

        self.tdx_api = None

        self.queue = Queue()
        self.active = False
        self.loaded = False

        self.thread = None

        self.symbol = None
        self.price_tick = 0.01

        self.renko_bars = {}  # bar_name: renko_bar

        self.setting = setting
        self.mongo_client = MongoData(host=self.setting.get('host', 'localhost'), port=self.setting.get('port', 27017))

        self.db_name = setting.get('db_name', STOCK_RENKO_DB_NAME)

        self.last_close_dt_dict = {}

        self.cache_folder = setting.get('cache_folder', None)

    def get_last_bar(self, renko_name):
        """
         通过mongo获取最新一个bar的数据
        :param renko_name:
        :return:
        """
        qryData = self.mongo_client.db_query_by_sort(db_name=self.db_name,
                                                     col_name=renko_name,
                                                     filter_dict={},
                                                     sort_name='datetime',
                                                     sort_type=-1,
                                                     limitNum=1)

        last_renko_close_dt = None
        bar = None
        for d in qryData:
            exchange = Exchange(d.get('exchange', 'LOCAL'))
            bar = RenkoBarData(gateway_name='',
                               symbol='',
                               exchange=exchange,
                               datetime=None)
            d.pop('_id', None)
            d.pop('exchange', None)
            d.update({'open_price': d.pop('open')})
            d.update({'close_price': d.pop('close')})
            d.update({'high_price': d.pop('high')})
            d.update({'low_price': d.pop('low')})
            bar.__dict__.update(d)
            bar.exchange = Exchange(d.get('exchange'))
            bar.color = Color(d.get('color'))

            last_renko_open_dt = d.get('datetime', None)
            if last_renko_open_dt is not None:
                last_renko_close_dt = last_renko_open_dt + timedelta(seconds=d.get('seconds', 0))
            break

        return bar, last_renko_close_dt

    def start(self, symbol, price_tick, height, start_date='2016-01-01', end_date='2099-01-01', refill=False):
        """启动重建工作"""
        self.symbol = symbol.upper()
        self.price_tick = price_tick
        if not isinstance(height, list):
            height = [height]

        db_last_close_dt = None
        for h in height:
            bar_name = '{}_{}'.format(self.symbol, h)
            bar_setting = {'name': bar_name,
                           'symbol': self.symbol,
                           'price_tick': price_tick}
            if isinstance(h, str) and 'K' in h:
                kilo_height = int(h.replace('K', ''))
                renko_height = price_tick * kilo_height
                bar_setting.update({'kilo_height': kilo_height})
            else:
                renko_height = price_tick * int(h)
                bar_setting.update({'renko_height': price_tick * int(h)})

            self.renko_bars[bar_name] = CtaRenkoBar(None, cb_on_bar=self.on_renko_bar, setting=bar_setting)

            if refill:
                bar, bar_last_close_dt = self.get_last_bar(bar_name)

                if bar:
                    self.write_log(u'重新添加最后一根{} Bar:{}'.format(bar_name, bar.__dict__))
                    # 只添加bar，不触发onbar事件
                    self.renko_bars[bar_name].add_bar(bar, is_init=True)
                    self.renko_bars[bar_name].update_renko_height(bar.close_price, renko_height)
                if bar_last_close_dt:
                    self.last_close_dt_dict.update({bar_name: bar_last_close_dt})
                    if db_last_close_dt:
                        db_last_close_dt = min(bar_last_close_dt, db_last_close_dt)
                    else:
                        db_last_close_dt = bar_last_close_dt

        # 创建tick更新线程
        self.thread = Thread(target=self.run, daemon=True)
        self.active = True
        self.thread.start()

        # 创建tdx连接
        self.tdx_api = TdxStockData(self)

        # 开始时间~结束时间
        start_day = datetime.strptime(start_date, '%Y-%m-%d')
        if isinstance(db_last_close_dt, datetime):
            if start_day < db_last_close_dt:
                start_day = db_last_close_dt
        end_day = datetime.strptime(end_date, '%Y-%m-%d')
        cur_trading_date = get_trading_date(datetime.now())
        if end_day >= datetime.now():
            end_day = datetime.strptime(cur_trading_date, '%Y-%m-%d') + timedelta(days=1)
            self.write_log(u'结束日期=》{}'.format(cur_trading_date))

        days = (end_day - start_day).days + 1
        self.write_log(u'数据范围：{}~{},{}天'.format(start_day.strftime('%Y-%m-%d'), end_day.strftime('%Y-%m-%d'), days))

        self.loaded = False
        last_tick_dt = None
        try:
            for i in range(days):
                trading_day = start_day + timedelta(days=i)
                self.write_log(u'获取{}分笔交易数据'.format(trading_day.strftime('%Y-%m-%d')))
                ret, result = self.tdx_api.get_history_transaction_data(self.symbol, trading_day.strftime('%Y%m%d'),
                                                                        self.cache_folder)
                if not ret:
                    self.write_error(u'取{} {}数据失败'.format(trading_day, self.symbol))
                    continue

                for data in result:
                    dt = data.get('datetime')

                    # 更新tick时间
                    if last_tick_dt is None:
                        last_tick_dt = dt
                    if last_tick_dt > dt:
                        continue
                    last_tick_dt = dt

                    # 如果tick时间比数据库的记录时间还早，丢弃
                    if db_last_close_dt:
                        if dt < db_last_close_dt:
                            continue
                    price = data.get('price')
                    volume = data.get('volume')
                    self.queue.put(item=(dt, price, volume))

                sleep(5)

        except Exception as ex:
            self.write_error(u'tdx下载数据异常:{}'.format(str(ex)))

        self.tdx_api = None
        self.write_log(u'加载完毕')
        self.loaded = True

        while (self.active):
            sleep(1)

        self.exit()

    def run(self):
        """处理tick数据"""
        self.write_log(u'启动处理tick线程')
        while self.active:
            try:
                dt, price, volume = self.queue.get(timeout=1)
                exchange = Exchange(get_stock_exchange(self.symbol))
                tick = TickData(gateway_name='tdx', symbol=self.symbol, datetime=dt, exchange=exchange)

                tick.date = tick.datetime.strftime('%Y-%m-%d')
                tick.time = tick.datetime.strftime('%H:%M:%S')
                tick.trading_day = get_trading_date(tick.datetime)
                tick.last_price = float(price)
                tick.volume = int(volume)

                for bar_name, renko_bar in self.renko_bars.items():
                    last_dt = self.last_close_dt_dict.get(bar_name, None)
                    if last_dt and tick.datetime < last_dt:
                        continue

                    if tick.datetime.hour == 9 and tick.datetime.minute < 30:
                        continue

                    renko_bar.on_tick(tick)
            except Exception as ex:
                if self.queue.empty() and self.loaded:
                    self.active = False
                    self.write_log(u'队列清空完成')
                elif str(ex) not in ['', 'Empty']:
                    traceback.print_exc()

        self.write_log(u'处理tick线程结束')

    def exit(self):
        self.check_index()
        self.write_log(u'重建结束')
        if self.thread:
            self.thread.join()

        try:
            self.thread = None
            self.queue = None
        except Exception:
            pass

        os.kill(os.getpid(), signal.SIGTERM)

    def on_renko_bar(self, bar: RenkoBarData, bar_name: str):
        """bar到达,入库"""
        flt = {'datetime': bar.datetime, 'open': bar.open_price}

        d = copy.copy(bar.__dict__)
        d.pop('row_data', None)
        # 数据转换
        d.update({'exchange': bar.exchange.value})
        d.update({'color': bar.color.value})
        d.update({'open': d.pop('open_price')})
        d.update({'close': d.pop('close_price')})
        d.update({'high': d.pop('high_price')})
        d.update({'low': d.pop('low_price')})

        try:
            self.mongo_client.db_update(self.db_name, bar_name, d, flt, True)
            self.write_log(u'new Renko Bar:{},dt:{},open:{},close:{},high:{},low:{},color:{}'
                           .format(bar_name, bar.datetime, bar.open_price, bar.close_price, bar.high_price,
                                   bar.low_price, bar.color.value))
        except Exception as ex:
            self.write_error(u'写入数据库异常:{},bar:{}'.format(str(ex), d))

    def update_last_dt(self, symbol, height):
        """更新最后的时间到主力合约设置"""

        bar, last_dt = self.get_last_bar('_'.join([symbol, str(height)]))
        if not last_dt:
            return

        flt = {'symbol': symbol}
        d = {'renko_{}'.format(height): last_dt.strftime('%Y-%m-%d %H:%M:%S') if isinstance(last_dt,
                                                                                            datetime) else last_dt}
        d.update(flt)
        d.update({'vn_exchange': get_stock_exchange(symbol)})
        d.update({'exchange': get_stock_exchange(symbol, False)})
        self.write_log(f'更新合约表中:{symbol}的renko bar {symbol}_{height}最后时间:{d}')
        self.mongo_client.db_update(db_name='Contract', col_name='stock_symbols', filter_dict=flt, data_dict=d,
                                    upsert=True,
                                    replace=False)

    def check_index(self):
        """检查索引是否存在，不存在就建立新索引"""
        for col_name in self.renko_bars.keys():
            self.write_log(u'检查{}.{}索引'.format(self.db_name, col_name))
            self.mongo_client.db_create_index(dbName=self.db_name, collectionName=col_name, indexName='datetime',
                                              sortType=1)
            self.mongo_client.db_create_multi_index(db_name=self.db_name, col_name=col_name,
                                                    index_list=[('datetime', 1), ('open', 1), ('close', 1),
                                                                ('volume', 1)])
            symbol, height = col_name.split('_')
            self.write_log(u'更新{}最后日期'.format(col_name))
            self.update_last_dt(symbol, height)

    def check_all_index(self):
        contracts = self.mongo_client.db_query(db_name='Contract', col_name='stock_symbols', filter_dict={},
                                               sort_key='symbol')

        for contract in contracts:
            symbol = contract.get('symbol')

            for height in HEIGHT_LIST:
                col_name = '{}_{}'.format(symbol, height)
                self.write_log(u'检查{}.{}索引'.format(self.db_name, col_name))
                self.mongo_client.db_create_index(dbName=self.db_name, collectionName=col_name, indexName='datetime',
                                                  sortType=1)
                self.mongo_client.db_create_multi_index(db_name=self.db_name, col_name=col_name,
                                                        index_list=[('datetime', 1), ('open', 1), ('close', 1),
                                                                    ('volume', 1)])
                symbol, height = col_name.split('_')
                self.write_log(u'更新{}最后日期'.format(col_name))
                self.update_last_dt(symbol, height)

    def export(self, symbol, height=10, start_date='2016-01-01', end_date='2099-01-01', csv_file=None):
        """ 导出csv"""
        qry = {'tradingDay': {'$gt': start_date, '$lt': end_date}}
        results = self.mongo_client.db_query_by_sort(db_name=self.db_name,
                                                     col_name='_'.join([symbol, str(height)]), filter_dict=qry,
                                                     sort_name='$natural', sort_type=1)

        if len(results) > 0:
            self.write_log(u'获取数据：{}条'.format(len(results)))
            header = None
            if csv_file is None:
                csv_file = 'renko_{}_{}_{}_{}.csv'.format(symbol, height, start_date.replace('-', ''),
                                                          end_date.replace('-', ''))
            f = open(csv_file, 'w', encoding=u'utf-8', newline="")
            dw = None
            for data in results:
                data.pop('_id', None)
                data['index'] = data.pop('datetime', None)
                data['trading_date'] = data.pop('trading_day', None)

                # 排除集合竞价导致的bar
                bar_start_dt = data.get('index')
                bar_end_dt = bar_start_dt + timedelta(seconds=int(data.get('seconds', 0)))
                if bar_start_dt.hour in [8, 20] and bar_end_dt.hour in [8, 20]:
                    continue

                if header is None and dw is None:
                    header = sorted(data.keys())
                    header.remove('index')
                    header.insert(0, 'index')
                    dw = csv.DictWriter(f, fieldnames=header, dialect='excel', extrasaction='ignore')
                    dw.writeheader()
                if dw:
                    dw.writerow(data)

            f.close()
            self.write_log(u'导出成功,文件:{}'.format(csv_file))
        else:
            self.write_error(u'导出失败')

    def export_refill_scripts(self):
        contracts = self.mongo_client.db_query(db_name='Contract', col_name='stock_symbols', filter_dict={},
                                               sort_key='symbol')

        for contract in contracts:
            symbol = contract.get('symbol')
            command = 'python refill_stock_renko.py {} {}'.format(self.setting.get('host', 'localhost'), symbol)
            self.write_log(command)

    def export_all(self, start_date='2016-01-01', end_date='2099-01-01', csv_folder=None):
        contracts = self.mongo_client.db_query(db_name='Contract', col_name='stock_symbols', filter_dict={},
                                               sort_key='symbol')

        for contract in contracts:
            symbol = contract.get('symbol')
            if contract.get('renko_3') is None or contract.get('renko_5') is None or contract.get('renko_10') is None:
                continue

            for height in HEIGHT_LIST:
                if csv_folder:
                    csv_file = os.path.abspath(os.path.join(csv_folder, 'renko_{}_{}_{}_{}.csv'
                                                            .format(symbol, height, start_date.replace('-', ''),
                                                                    end_date.replace('-', ''))))
                else:
                    csv_file = None
                self.export(symbol, height, start_date, end_date, csv_file)
