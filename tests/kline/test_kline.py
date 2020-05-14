# flake8: noqa
########################################################################
# 功能测试
########################################################################
import sys
from vnpy.trader.ui.kline.kline import *

if __name__ == '__main__':
    app = QtWidgets.QApplication([])  # QtGui.QApplication(sys.argv)

    # 界面设置
    cfgfile = QtCore.QFile('css.qss')
    cfgfile.open(QtCore.QFile.ReadOnly)
    styleSheet = cfgfile.readAll()
    styleSheet = str(styleSheet)
    app.setStyleSheet(styleSheet)

    # K线界面
    try:
        ui = KLineWidget(display_sub=True)
        ui.show()
        ui.KLtitle.setText('I99', size='20pt')
        ui.add_indicator(indicator='ma5', is_main=True)
        ui.add_indicator(indicator='ma10', is_main=True)
        ui.add_indicator(indicator='ma18', is_main=True)
        ui.add_indicator(indicator='sk', is_main=False)
        ui.add_indicator(indicator='sd', is_main=False)
        df = pd.read_csv('test_data/I99_d.csv')
        df = df.set_index(pd.DatetimeIndex(df['datetime']))
        ui.loadData(df, main_indicators=['ma5', 'ma10', 'ma18'], sub_indicators=['sk', 'sd'])

        #df_trade = pd.read_csv('test_data/trade_list.csv')
        #ui.add_signals(df_trade)

        df_tns = pd.read_csv('test_data/tns.csv')
        ui.add_trans_df(df_tns)

        # df_markup = pd.read_csv('dist.csv')
        # df_markup = df_markup[['datetime','price','operation']]
        # df_markup.rename(columns={'operation':'markup'},inplace=True)
        # ui.add_markups(df_markup=df_markup, exclude_list=['buy','short','sell','cover'])
        #
        app.exec_()

    except Exception as ex:
        print(u'exception:{},trace:{}'.format(str(ex), traceback.format_exc()))
