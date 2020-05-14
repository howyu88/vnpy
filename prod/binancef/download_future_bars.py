# flake8: noqa


import os
import sys

# 将repostory的目录i，作为根目录，添加到系统环境中。
ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT_PATH not in sys.path:
    sys.path.append(ROOT_PATH)
    print(f'append {ROOT_PATH} into sys.path')

from datetime import datetime
from vnpy.data.binance.binance_future_data import BinanceFutureData, HistoryRequest, Exchange, Interval

# 获取币安合约交易的所有期货合约
future_data = BinanceFutureData()
contracts = BinanceFutureData.load_contracts()
if len(contracts) == 0:
    future_data.save_contracts()
    contracts = BinanceFutureData.load_contracts()

# 逐一合约进行下载
for vt_symbol, contract_info in contracts.items():
    symbol = contract_info.get('symbol')
    req = HistoryRequest(
        symbol=symbol,
        exchange=Exchange(contract_info.get('exchange')),
        interval=Interval.MINUTE,
        start=datetime(year=2019, month=1, day=1)
    )

    bars = future_data.get_bars(req=req, return_dict=True)

    file_name = os.path.abspath(os.path.join(
        ROOT_PATH,
        'bar_data',
        '{}_{}_1m.csv'.format(req.symbol, req.start.strftime('%Y%m%d'))))
    future_data.export_to(bars, file_name=file_name)
