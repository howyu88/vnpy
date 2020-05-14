# flake8: noqa

import os
import sys

# 将repostory的目录，作为根目录，添加到系统环境中。
VNPY_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..' ))
sys.path.append(VNPY_ROOT)
print(f'append {VNPY_ROOT} into sys.path')

from datetime import datetime

from vnpy.app.cta_strategy_pro.portfolio_testing import PortfolioTestingEngine
from vnpy.trader.utility import load_json

def get_symbol_configs(json_file_name, bar_file_format):
    """
    根据文件获取合约的配置
    :param json_file_name:
    :param bar_file_format:
    :return: dict
    """
    config_dict = load_json(json_file_name)
    for underlying_symbol in list(config_dict.keys()):
        config = config_dict.pop(underlying_symbol, {})
        config.pop('mi_symbol', None)
        config.pop('full_symbol', None)
        config.update({
            'product': "期货",
            'commission_rate': 0.0001 if underlying_symbol not in ['T', 'TF'] else 5,
            'bar_file': bar_file_format.format(underlying_symbol)})
        config_dict.update({f'{underlying_symbol}99': config})

    return config_dict

# 回测引擎参数
test_settings = {}

test_settings['name'] = 'portfolio_test_{}'.format(datetime.now().strftime('%m%d_%H%M'))

# 测试时间段, 从开始日期计算，过了init_days天，才全部激活交易
test_settings['start_date'] = '20190101'
test_settings['init_days'] = 10
test_settings['end_date'] = '20200101'

# 测试资金相关, 资金最大仓位， 期初资金
test_settings['percent_limit'] = 60
test_settings['init_capital'] = 2000000

# 测试日志相关
test_settings['debug'] = False

# 配置是绝对路径（或与当前运行目录的相对路径）
test_settings['data_path'] = 'data'
test_settings['logs_path'] = 'log'

# 测试数据文件相关(可以从test_symbols加载，或者自定义）
test_settings['bar_interval_seconds'] = 60   # 回测数据的秒周期

# 从配置文件中获取回测合约的基本信息，并更新bar的路径
test_settings['symbol_datas'] = get_symbol_configs(
    json_file_name=os.path.abspath(os.path.join(VNPY_ROOT, 'vnpy', 'data', 'tdx', 'future_contracts.json')),
    bar_file_format=VNPY_ROOT + '/bar_data/{}99_20160101_1m.csv'
)

# 读取组合回测策略的参数列表
strategy_settings = load_json('cta_strategy_pro_setting.json')

# 创建事件引擎
from vnpy.event.engine import EventEngine
event_engine = EventEngine()
event_engine.start()

# 创建组合回测引擎
engine = PortfolioTestingEngine(event_engine)

engine.prepare_env(test_settings)
engine.run_portfolio_test(strategy_settings)
# 回测结果，保存
result_info = engine.show_backtesting_result(is_plot_daily=True)

if event_engine:
    event_engine.stop()

os._exit(0)
