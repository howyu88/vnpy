# flake8: noqa
"""
多周期显示K线，
时间点同步
华富资产/李来佳
"""

import sys
import os
import ctypes
import platform
system = platform.system()
os.environ["VNPY_TESTING"] = "1"

# 将repostory的目录，作为根目录，添加到系统环境中。
ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..' , '..'))
sys.path.append(ROOT_PATH)

from vnpy.trader.ui.kline.crosshair import Crosshair
from vnpy.trader.ui.kline.kline import *
from vnpy.trader.ui.kline.ui_snapshot import UiSnapshot
if __name__ == '__main__':

    try:
        from vnpy.trader.ui import create_qapp

        qApp = create_qapp()

        snapshot_file = os.path.abspath(os.path.join(ROOT_PATH, 'prod', 'binance01', 'data', 'snapshots', 'triple_ma_btc_M5', '20200322_205345.pkb2'))
        ui_snapshot = UiSnapshot()
        ui_snapshot.show(snapshot_file)
        sys.exit(qApp.exec_())

    except Exception as ex:
        print(u'exception:{},trace:{}'.format(str(ex), traceback.format_exc()))
