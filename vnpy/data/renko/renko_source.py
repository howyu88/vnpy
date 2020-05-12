# encoding: UTF-8

import sys
import copy
from datetime import datetime, timedelta

from vnpy.data.mongo.mongo_data import MongoData
from vnpy.trader.constant import Exchange
from vnpy.trader.object import TickData, RenkoBarData
from vnpy.trader.utility import get_trading_date, extract_vt_symbol
from vnpy.data.renko.config import FUTURE_RENKO_DB_NAME


class RenkoSource(object):
    """
    砖图数据源
    期货： FUTURE_RENKO_DB_NAME
    股票:  STOCK_RENKO_DB_NAME
    """

    def __init__(self, strategy=None, setting={}):

        self.tdx_api = None
        self.strategy = strategy

        self.setting = setting
        self.mongo_client = MongoData(host=self.setting.get('host', 'localhost'), port=self.setting.get('port', 27017))

        self.db_name = setting.get('db_name', FUTURE_RENKO_DB_NAME)

    def write_log(self, content):
        if self.strategy:
            self.strategy.write_log(content)
        else:
            print(content)

    def write_error(self, content):
        if self.strategy:
            self.strategy.writeCtaError(content)
        else:
            print(content, file=sys.stderr)

    def get_bars(self, symbol, height=10, callback=None, start_date=None, limit_num=2000):
        """
        获取renko_bar"
        :param symbol:
        :param height:
        :param callback:
        :param start_date: 开始日期
        :param limit_num:  限制数量, 0 为不限制
        :return:
        """
        qry = {}
        if start_date:
            qry = {'trading_day': {'$gt': start_date}}
        if '.' in symbol:
            symbol, exchange = extract_vt_symbol(symbol)
        else:
            exchange = Exchange.LOCAL
        results = self.mongo_client.db_query_by_sort(db_name=self.db_name, col_name='_'.join([symbol, str(height)]),
                                                     filter_dict=qry, sort_name='$natural', sort_type=-1,
                                                     limitNum=limit_num)
        bars = []
        if len(results) > 0:
            self.write_log(u'获取{}_{}数据：{}条'.format(symbol, height, len(results)))
            results.reverse()
            for data in results:
                data.pop('_id', None)
                # 排除集合竞价导致的bar
                bar_start_dt = data.get('datetime')
                bar_end_dt = bar_start_dt + timedelta(seconds=int(data.get('seconds', 0)))
                if bar_start_dt.hour in [8, 20] and bar_end_dt.hour in [8, 20]:
                    continue

                bar = RenkoBarData(
                    gateway_name='ds',
                    symbol=symbol,
                    exchange=exchange,
                    datetime=bar_start_dt
                )
                bar.__dict__.update(data)

                # 兼容vnpy2.0得写法
                if 'open' in data:
                    bar.open_price = data.get('open')
                if 'close' in data:
                    bar.close_price = data.get('close')
                if 'high' in data:
                    bar.high_price = data.get('high')
                if 'low' in data:
                    bar.low_price = data.get('low')

                if callback:
                    callback(copy.copy(bar))

                bars.append(bar)

            return True, bars
        else:
            self.write_error(u'下载数据失败')
            return False, bars

    def get_ticks(self, symbol, min_diff=1, start_dt=None):
        """
        获取合约的tick
        :param symbol:
        :param start_dt: datetime， 开始时间
        :return:
        """
        # 创建tdx连接
        from vnpy.data.tdx.tdx_future_data import TdxFutureData
        self.tdx_api = TdxFutureData(self.strategy)

        if '.' in symbol:
            symbol, exchange = extract_vt_symbol(symbol)
        else:
            exchange = Exchange.LOCAL

        if start_dt is None:
            start_dt = datetime.now() - timedelta(days=1)

        # 开始时间~结束时间
        start_day = start_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        cur_trading_date = get_trading_date(datetime.now())
        end_day = datetime.strptime(cur_trading_date, '%Y-%m-%d') + timedelta(days=1)
        self.write_log(u'结束日期=》{}'.format(cur_trading_date))

        days = (end_day - start_day).days + 1
        self.write_log(u'数据范围：{}~{},{}天'.format(start_day.strftime('%Y-%m-%d'), end_day.strftime('%Y-%m-%d'), days))

        last_tick_dt = None
        ticks = []
        for i in range(days):
            trading_day = start_day + timedelta(days=i)
            self.write_log(u'获取{}分笔交易数据'.format(trading_day.strftime('%Y-%m-%d')))
            ret, result = self.tdx_api.get_history_transaction_data(symbol, trading_day.strftime('%Y%m%d'))
            if not ret:
                self.write_error(u'取{} {}数据失败'.format(trading_day, symbol))
                continue

            for data in result:
                dt = data.get('datetime')
                # 更新tick时间
                if last_tick_dt is None:
                    last_tick_dt = dt
                if last_tick_dt > dt:
                    continue
                last_tick_dt = dt

                # 如果tick时间比start_dt的记录时间还早，丢弃
                if dt < start_dt:
                    continue
                price = data.get('price')
                volume = data.get('volume')

                tick = TickData(
                    gateway_name='ds',
                    symbol=symbol,
                    exchange=exchange,
                    datetime=dt
                )

                tick.date = tick.datetime.strftime('%Y-%m-%d')
                tick.time = tick.datetime.strftime('%H:%M:%S')
                tick.volume = volume
                tick.last_price = float(price)
                tick.ask_price_1 = tick.last_price + min_diff
                tick.ask_volume_1 = volume
                tick.bid_price_1 = tick.last_price - min_diff
                tick.bid_volume_1 = volume
                tick.trading_day = trading_day.strftime('%Y-%m-%d')

                ticks.append(tick)

        return len(ticks) > 0, ticks
