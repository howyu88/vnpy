# flake8: noqa

# 功能测试
########################################################################
import sys
from vnpy.trader.ui import create_qapp, QtCore
from vnpy.trader.ui.kline.kline_widgets import *

def display_multi_window():
    qApp = create_qapp()

    settings = []
    collections = ['RB99_5', 'RB99_10']
    for collection in collections:
        s = {
            'kline_name': collection,
            'mongo':
                {
                    'host': 'localhost',
                    'port': 27017,
                    'db': 'Renko_Db',
                    'collection': collection
                },
            'live':
                {
                    'exchange': 'x_fanout_md_renko'
                }
        }
        settings.append(s)

    w = MultiKlineWindow(parent=None, settings=settings)
    w.showMaximized()
    sys.exit(qApp.exec_())


if __name__ == '__main__':
    try:
        display_multi_window()

    except Exception as ex:
        print(u'exception:{},trace:{}'.format(str(ex), traceback.format_exc()))
