三均线策略测试目录

export_triple_ma_bars.py
    
    演示如何通过tdx一分钟bar数据，生成我们需要的x分钟K线数据和指标。
    - 一分钟所需数据源为 项目目录/bar_data/{合约}_20160101_1m.csv
    - 生成数据输出为csv文件，里面包括K线高低开平，以及主图附图指标（三条均线），附图指标（2个摆动指标）。
    - 输出文件存储在data子目录中，供后续使用

run_single_test_v1.py
    
    演示如何回测三均线策略 v1 版本
    - 策略：项目目录/app/cta_strategy_pro/strategies/strategy_triple_ma_v1.py
    - 使用组合回测引擎
    - 数据源为 项目目录/bar_data/{合约}_20160101_1m.csv    
    - 期货商品合约的基础配置参数，将使用 项目目录/vnpy/data/tdx/future_contracts.json
    - 测试结果，放在 log/{组合回测实例名}/
    
run_single_test_v2.py
    
    演示如何回测三均线策略 v2 版本
    - 策略：项目目录/app/cta_strategy_pro/strategies/strategy_triple_ma_v2.py
    - 使用组合回测引擎
    - 数据源为 项目目录/bar_data/{合约}_20160101_1m.csv
    - 期货商品合约的基础配置参数，将使用 项目目录/vnpy/data/tdx/future_contracts.json
    - 测试结果，放在 log/{组合回测实例名}/
    
ui_triple_ma_kline.py

    演示如何回放测试结果
    - 加载K线数据和指标。 这里数据可预先通过export_triple_ma_bars.py生成
    - 加载回测成交记录trade.csv 和事务过程tns.csv
