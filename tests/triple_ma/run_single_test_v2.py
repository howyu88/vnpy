# flake8: noqa

import os
import sys
from copy import copy

# 将repostory的目录，作为根目录，添加到系统环境中。
VNPY_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', ))
if VNPY_ROOT not in sys.path:
    sys.path.append(VNPY_ROOT)
    print(f'append {VNPY_ROOT} into sys.path')

from datetime import datetime
from vnpy.app.cta_strategy_pro.portfolio_testing import single_test
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
test_setting = {}

test_setting['name'] = 'triple_mav2_test_{}'.format(datetime.now().strftime('%m%d_%H%M'))

# 测试时间段, 从开始日期计算，过了init_days天，才全部激活交易
test_setting['start_date'] = '20180101'
test_setting['init_days'] = 30
test_setting['end_date'] = '20190101'

# 测试资金相关, 资金最大仓位， 期初资金
test_setting['percent_limit'] = 20
test_setting['init_capital'] = 2000000

# 测试日志相关， Ture，开始详细日志， False, 只记录简单日志
test_setting['debug'] = False

# 配置是当前运行目录的相对路径
test_setting['data_path'] = 'data'
test_setting['logs_path'] = 'log'

# 测试数据文件相关(可以从test_symbols加载，或者自定义）
test_setting['bar_interval_seconds'] = 60   # 回测数据的秒周期

# 从配置文件中获取回测合约的基本信息，并更新bar的路径
symbol_datas = get_symbol_configs(
    json_file_name=os.path.abspath(os.path.join(VNPY_ROOT, 'vnpy', 'data', 'tdx', 'future_contracts.json')),
    bar_file_format=VNPY_ROOT + '/bar_data/{}99_20160101_1m.csv'
)

test_setting['symbol_datas'] = symbol_datas

"""
# 这里是读取账号的cta strategy pro json文件，作为一个组合
# 读取组合回测策略的参数列表
strategy_setting = load_json('cta_strategy_pro_setting.json')


task_id = str(uuid1())
print(f'添加celery 任务：{task_id}')
execute.apply_async(kwargs={'func': 'vnpy.app.cta_strategy_pro.portfolio_testing.single_test',
                                'test_setting': test_setting,
                                'strategy_setting': strategy_setting},
                                task_id=task_id)

"""

# 创建回测任务
count = 0

symbol = 'J99'
symbol_info = symbol_datas.get(symbol)
underlying_symbol = symbol_info.get('underlying_symbol')

# 更新测试名称
test_setting.update({'name': test_setting['name'] + f"_{symbol}"})
#
strategy_setting = {
    f"triple_ma_{symbol}": {
        "class_name": "Strategy_TripleMa_v2",
        "vt_symbol": f"{symbol}",
        "auto_init": True,
        "setting": {
            "backtesting": True,
            "class_name": "Strategy_TripleMa_v2",
            "max_invest_percent": 10,
            "add_pos_above_price_count": 1,
            "add_pos_under_price_count": 2,
            "x_minute": 15
        }
    },
    "triple_ma_JM": {
        "class_name": "Strategy_TripleMa_v2",
        "vt_symbol": "JM99",
        "auto_init": True,
        "setting": {
            "backtesting": True,
            "class_name": "Strategy_TripleMa_v2",
            "max_invest_percent": 10,
            "add_pos_above_price_count": 0,
            "add_pos_under_price_count": 2,
            "x_minute": 15
        }
    }
}

single_test(test_setting=test_setting, strategy_setting=strategy_setting)


