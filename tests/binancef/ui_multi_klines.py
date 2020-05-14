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

if __name__ == '__main__':

    # K线界面
    try:
        kline_settings = {
            "M5":
                {
                    "data_file": "log/triple_mav2_test_0317_1310_BTCUSDT/triple_ma_BTCUSDT.BINANCE_M5.csv",
                    "main_indicators": [
                        "ma5",
                        "ma20"
                    ],
                    "sub_indicators": [
                        "dif",
                        "dea",
                        "macd"
                    ],
                    "dist_file": "log/triple_mav2_test_0317_1310_BTCUSDT/triple_ma_BTCUSDT.BINANCE_dist.csv",
                    "dist_include_list": ["buy"]
                },
            "M15":
                {
                    "data_file": "log/triple_mav2_test_0317_1310_BTCUSDT/triple_ma_BTCUSDT.BINANCE_M15.csv",
                    "main_indicators": [
                        "ma5",
                        "ma20"
                    ],
                    "sub_indicators": [
                        "dif",
                        "dea",
                        "macd"
                    ],
                    "dist_file": "log/triple_mav2_test_0317_1310_BTCUSDT/triple_ma_BTCUSDT.BINANCE_dist.csv",
                    "dist_include_list": ["buy"]
                },
            "M30":
                {
                    "data_file": "log/triple_mav2_test_0317_1310_BTCUSDT/triple_ma_BTCUSDT.BINANCE_M30.csv",
                    "main_indicators": [
                        "ma5",
                        "ma20"
                    ],
                    "sub_indicators": [
                        "dif",
                        "dea",
                        "macd"
                    ],
                    "dist_file": "log/triple_mav2_test_0317_1310_BTCUSDT/triple_ma_BTCUSDT.BINANCE_dist.csv",
                    "dist_include_list": ["buy"]
                }
        }
        display_multi_grid(kline_settings)

    except Exception as ex:
        print(u'exception:{},trace:{}'.format(str(ex), traceback.format_exc()))
