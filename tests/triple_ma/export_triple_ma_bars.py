# flake8: noqa
# AUTHOR:李来佳
# WeChat/QQ: 28888502

import sys
import os
# 将repostory的目录，作为根目录，添加到系统环境中。
VNPY_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', ))
if VNPY_ROOT not in sys.path:
    sys.path.append(VNPY_ROOT)
    print(f'append {VNPY_ROOT} into sys.path')

from vnpy.app.cta_strategy_pro.cta_line_bar import *
from vnpy.trader.utility import get_underlying_symbol, extract_vt_symbol, round_to


class ExportStrategy(object):
    #  读取1分钟原始k线记录，导出指定周期的三均线的K线数据
    def __init__(self, price_tick, underly_symbol, vt_symbol):
        self.price_tick = price_tick
        self.underly_symbol = underly_symbol
        self.symbol, self.exchange = extract_vt_symbol(vt_symbol)

        # 定义分钟周期
        self.klineX = None

        # 灌入数据的分钟周期
        self.TMinuteInterval = 1

        self.save_x_bars = []

    def createLineMinX(self, x, k_type=CtaLineBar, ma_lens=[10, 20, 120]):
        # 创建分钟 K线
        # k_type：
        #  CtaLineBar (按照时间跨度记录分钟K线）
        #  CtaMinuteBar (按照1分钟累计的分钟k线）

        lineMinXSetting = {}
        lineMinXSetting['name'] = u'M{}'.format(x)
        lineMinXSetting['interval'] = Interval.MINUTE
        lineMinXSetting['bar_interval'] = x

        # 三均线参数
        lineMinXSetting['para_ma1_len'] = ma_lens[0]
        lineMinXSetting['para_ma2_len'] = ma_lens[1]
        lineMinXSetting['para_ma3_len'] = ma_lens[2]

        # 摆动指标
        lineMinXSetting['para_active_skd'] = True

        lineMinXSetting['price_tick'] = self.price_tick
        lineMinXSetting['underly_symbol'] = self.underly_symbol

        self.klineX = k_type(self, self.on_bar_x, lineMinXSetting)

    def on_bar(self, bar):
        # print(u'tradingDay:{},dt:{},o:{},h:{},l:{},c:{},v:{}'.format(bar.tradingDay,bar.datetime, bar.open, bar.high, bar.low, bar.close, bar.volume))

        if self.klineX:
            self.klineX.add_bar(bar, bar_freq=self.TMinuteInterval)

    def on_bar_x(self, bar):
        self.write_log(self.klineX.get_last_bar_str())

        self.save_x_bars.append({
            'datetime': bar.datetime,
            'open': bar.open_price,
            'high': bar.high_price,
            'low': bar.low_price,
            'close': bar.close_price,
            'turnover': 0,
            'volume': bar.volume,
            'open_interest': 0,
            'ma{}'.format(self.klineX.para_ma1_len): self.klineX.line_ma1[-1] if len(
                self.klineX.line_ma1) > 0 else bar.close_price,
            'ma{}'.format(self.klineX.para_ma2_len): self.klineX.line_ma2[-1] if len(
                self.klineX.line_ma2) > 0 else bar.close_price,
            'ma{}'.format(self.klineX.para_ma3_len): self.klineX.line_ma3[-1] if len(
                self.klineX.line_ma3) > 0 else bar.close_price,
            'sk': self.klineX.line_sk[-1] if len(self.klineX.line_sk) > 0 else 0,
            'sd': self.klineX.line_sd[-1] if len(self.klineX.line_sd) > 0 else 0
        })

    def on_tick(self, tick):
        print(u'{0},{1},ap:{2},av:{3},bp:{4},bv:{5}'.format(tick.datetime, tick.lastPrice, tick.askPrice1,
                                                            tick.askVolume1, tick.bidPrice1, tick.bidVolume1))

    def write_log(self, content):
        print(content)

    def save_data(self):
        """保存数据"""
        if len(self.save_x_bars) > 0:
            outputFile = 'data/{}_{}.csv'.format(self.symbol, self.klineX.name)
            with open(outputFile, 'w', encoding='utf8', newline='') as f:
                fieldnames = ['datetime', 'open', 'high', 'low', 'close', 'turnover', 'volume', 'open_interest',
                              'ma{}'.format(self.klineX.para_ma1_len),
                              'ma{}'.format(self.klineX.para_ma2_len),
                              'ma{}'.format(self.klineX.para_ma3_len),
                              'sk', 'sd']
                writer = csv.DictWriter(f=f, fieldnames=fieldnames, dialect='excel')
                writer.writeheader()
                for row in self.save_x_bars:
                    writer.writerow(row)


if __name__ == '__main__':

    t = ExportStrategy(price_tick=1, underly_symbol='J', vt_symbol='J99.DCE')

    # 创建M5K线
    #t.createLineMinX(x=5)

    # 创建M30线
    t.createLineMinX(x=30, k_type=CtaMinuteBar)

    filename = os.path.abspath(os.path.join(VNPY_ROOT, 'bar_data', f'{t.symbol}_20160101_1m.csv'))

    barTimeInterval = 60  # 60秒
    price_tick = t.price_tick  # 回测数据的最小跳动

    import csv

    csvfile = open(filename, 'r', encoding='utf8')
    reader = csv.DictReader((line.replace('\0', '') for line in csvfile), delimiter=",")
    last_tradingDay = None
    for row in reader:
        try:

            barEndTime = datetime.strptime(row['datetime'], '%Y-%m-%d %H:%M:%S')

            # 使用Bar的开始时间作为datetime
            bar_datetime = barEndTime - timedelta(seconds=barTimeInterval)

            bar = BarData(
                gateway_name='TDX',
                symbol=t.symbol,
                exchange=t.exchange,
                open_price=round_to(float(row['open']), price_tick),
                high_price=round_to(float(row['high']), price_tick),
                low_price=round_to(float(row['low']), price_tick),
                close_price=round_to(float(row['close']), price_tick),
                volume=float(row['volume']),
                datetime=bar_datetime,
                trading_day=row['trading_day']
            )

            t.on_bar(bar)

        except Exception as ex:
            t.write_log(u'{0}:{1}'.format(Exception, ex))
            traceback.print_exc()
            break

    t.save_data()
