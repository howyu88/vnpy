# flake8: noqa
"""
单周期显示K线，
加载logs目录下最新的回测结果交易数据
李来佳
"""

import sys
import os
import ctypes
import platform

system = platform.system()

# 将repostory的目录，作为根目录，添加到系统环境中。
ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
sys.path.append(ROOT_PATH)

from vnpy.trader.ui.kline.crosshair import Crosshair
from vnpy.trader.ui.kline.kline import *
from vnpy.trader.ui import create_qapp

if __name__ == '__main__':
    qApp = create_qapp('kline')

    # K线界面
    try:
        ui = KLineWidget(display_vol=False, display_sub=True)
        ui.show()

        csv_file_name = 'J99_M30'
        test_task = 'triple_mav2_test_0223_2026_J99'
        ma1 = 'ma10'
        ma2 = 'ma20'
        ma3 = 'ma120'

        trade_file_name = f'{test_task}_trade'
        tns_file_name = 'triple_ma_J99_tns'

        # 显示标题
        ui.KLtitle.setText(csv_file_name, size='20pt')

        # 主图指标（三均线）
        ui.add_indicator(indicator=ma1, is_main=True)
        ui.add_indicator(indicator=ma2, is_main=True)
        ui.add_indicator(indicator=ma3, is_main=True)

        # 副图指标（摆动）
        ui.add_indicator(indicator='sk', is_main=False)
        ui.add_indicator(indicator='sd', is_main=False)

        # 加载k线数据+主图指标数据+副图指标数据
        df = pd.read_csv('data/{}.csv'.format(csv_file_name))
        df = df.set_index(pd.DatetimeIndex(df['datetime']))

        ui.loadData(df,
                    main_indicators=[ma1, ma2, ma3],
                    sub_indicators=['sk', 'sd'])

        # 加载交易记录
        trade_csv_file = os.path.abspath(os.path.join(os.curdir, 'log', test_task, '{}.csv'.format(trade_file_name)))
        if os.path.exists(trade_csv_file):
            df_trade = pd.read_csv(trade_csv_file)
            ui.add_trades(df_trade)

        # 加载事务(多-》空-》多）画线
        tns_csv_file = os.path.abspath(os.path.join(os.curdir, 'log', test_task, '{}.csv'.format(tns_file_name)))
        if os.path.exists(tns_csv_file):
            df_tns = pd.read_csv(tns_csv_file)
            ui.add_trans_df(df_tns)

        qApp.exec_()

    except Exception as ex:
        print(u'exception:{},trace:{}'.format(str(ex), traceback.format_exc()))
