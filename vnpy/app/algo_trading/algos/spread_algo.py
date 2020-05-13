# encoding: UTF-8

from __future__ import division
from collections import OrderedDict

import os
import traceback
import copy
from datetime import datetime
import decimal

from vnpy.trader.constant import (Direction, Offset, Status, Exchange)
from vnpy.trader.object import TradeData, OrderData
from vnpy.trader.engine import BaseEngine
from vnpy.event import Event
from vnpy.trader.event import (EVENT_ORDER, EVENT_TRADE)
from vnpy.trader.utility import get_underlying_symbol, get_folder_path, append_data, extract_vt_symbol
from vnpy.app.algo_trading.template import AlgoTemplate


########################################################################
class spreadAlgo(AlgoTemplate):
    """
    价差价比交易算法，用于套利
    # 增加下单前判断是否涨停和跌停。
    """

    templateName = u'SpreadTrading套利'

    # ----------------------------------------------------------------------
    def __init__(self, algo_engine, algo_name, setting):
        """Constructor"""
        super().__init__(algo_engine, algo_name, setting)

        self.write_log(u'配置参数:\n{}'.format(setting))
        # 配置参数
        self.strategy_name = str(setting['strategy_name'])  # 来自调用的策略实例的名称
        self.order_vt_symbol = str(setting['order_vt_symbol'])  # 价差/价比合约的名称 j1905-1-rb1905-5-BJ.SPD
        self.order_symbol, self.exchange = extract_vt_symbol(self.order_vt_symbol)
        self.gateway_name = setting.get('gateway_ame', "")
        self.order_command = str(setting['order_command'])  # 交易命令 buy/sell/short/cover

        self.order_req_price = float(setting['order_price'])  # 委托价差
        self.order_req_volume = float(setting['order_volume'])  # 委托数量
        self.timer_interval = int(setting['timer_interval'])  # 检查成交的时间间隔（秒)

        # 初始化
        self.active_traded_volume = 0  # 主动腿的成交数量
        self.passive_traded_volume = 0  # 被动腿的成交数量
        self.active_traded_avg_price = 0  # 主动腿的成交均价
        self.passive_traded_avg_price = 0  # 被动腿的成交均价
        self.active_orderID = []  # 主动委托号，一个或多个
        self.passive_orderID = []  # 被动委托号
        self.active_orderID_history = ''  # 历史主动委托号
        self.passive_orderID_history = ''  # 历史被动委托号
        self.active_order_avg_price = 0  # 主动腿的报单均价
        self.passive_order_avg_price = 0  # 被动腿的报单均价
        self.active_order_volume = 0  # 主动腿的报单数量
        self.passive_order_volume = 0  # 被动腿的报单数量

        self.netPos = 0  # 净持仓
        self.count = 0  # 运行计数
        self.entrust = False  # 是否在正在交易中

        self.last_tick = None  # 最新的价差/价比价格
        self.last_active_tick = None  # 最新的主动腿价格
        self.last_passive_tick = None  # 最新的被动腿价格

        # 检查价差合约的名称
        if self.exchange != Exchange.SPD:
            self.write_error(u'套利合约代码错误, 参考格式: j1905-1-rb1905-5-BJ.SPD')
            return
        self.algo_order = self.get_algo_order()

        self.active_vt_symbol = self.get_vt_symbol(setting.get('leg1_symbol'))  # 主动腿的真实合约
        self.active_ratio = int(setting.get('leg1_ratio', 1))  # 主动腿/leg1的下单比例
        self.passive_vt_symbol = self.get_vt_symbol(setting.get('leg2_symbol'))  # 被动腿真实合约
        self.passive_ratio = int(setting.get('leg2_ratio', 1))  # 被动腿/leg2的下单比例
        self.is_spread = setting.get('is_spread', False)  # 价差交易
        self.is_ratio = setting.get('is_ratio', False)  # 价比交易

        if not self.is_spread and not self.is_ratio:
            self.write_log(u'套利配置中，缺少is_spread 或 is_ratio')
            return

        # 需要交易的数量
        self.active_target_volume = self.order_req_volume * self.active_ratio
        self.passive_target_volume = self.order_req_volume * self.passive_ratio

        # 订阅合约
        self.subscribe(self.active_vt_symbol)
        self.subscribe(self.passive_vt_symbol)
        self.subscribe(self.order_vt_symbol)

        # 获取合约基本信息
        self.active_contract = self.get_contract(self.active_vt_symbol)
        self.passive_contract = self.get_contract(self.passive_vt_symbol)

        self.put_parameters_event()
        self.put_variables_event()
        self.write_log('{}.__init__()'.format(self.algo_name))

        # 委托下单得费用满足
        self.invest_money_enough = False

    def get_vt_symbol(self, symbol):
        """获取vt_symbol"""
        if '.' in symbol:
            return symbol

        contract = self.get_contract(symbol)

        if contract:
            return contract.vt_symbol
        else:
            self.write_error(f'获取不到{symbol}合约信息')
            return symbol

    def get_algo_order(self):
        """获取算法的委托单"""
        order = OrderData(
            gateway_name=self.gateway_name,
            symbol=self.order_symbol,
            exchange=self.exchange,
            price=self.order_req_price,
            volume=self.order_req_volume,
            traded=0,
            orderid=self.algo_name
        )

        if self.order_command.lower() == 'buy':
            order.direction = Direction.LONG
            order.offset = Offset.OPEN
        elif self.order_command.lower() == 'short':
            order.direction = Direction.SHORT
            order.offset = Offset.OPEN
        elif self.order_command.lower() == 'sell':
            order.direction = Direction.SHORT
            order.offset = Offset.CLOSE
        elif self.order_command.lower() == 'cover':
            order.direction = Direction.LONG
            order.offset = Offset.CLOSE

        order.status = Status.SUBMITTING
        return order

    # ----------------------------------------------------------------------
    def on_tick(self, tick):
        """"""

        if not self.active:
            return

        # 更新三个合约的tick
        if tick.vt_symbol == self.order_vt_symbol:
            self.last_tick = tick
        elif tick.vt_symbol == self.active_vt_symbol:
            self.last_active_tick = tick
        elif tick.vt_symbol == self.passive_vt_symbol:
            self.last_passive_tick = tick

        # Tick 未更新完毕
        if self.last_tick is None or self.last_passive_tick is None or self.last_active_tick is None:
            return

        # 检查资金是否满足开仓
        if not self.invest_money_enough:
            if self.order_command.lower() in ['buy', 'short']:
                if self.check_invest_money():
                    self.invest_money_enough = True
                else:
                    return
            else:
                self.invest_money_enough = True

        # 检查主动腿合约/被动腿合约，是否接近涨停/跌停价
        if self.active_traded_volume == 0 and self.passive_traded_volume == 0:
            if self.active_contract is not None and self.passive_contract is not None:
                if 0 < self.last_active_tick.limit_up < self.last_active_tick.last_price + self.active_contract.pricetick * 10:
                    self.write_log(
                        u'{}合约价格{} 接近涨停价{} 10个跳,不处理'.format(self.active_vt_symbol, self.last_active_tick.last_price,
                                                            self.last_active_tick.limit_up))
                    self.cancel_algo()
                    self.stop()
                    return

                if 0 < self.last_passive_tick.limit_up < self.last_passive_tick.last_price + self.passive_contract.pricetick * 10:
                    self.write_log(
                        u'{}合约价格{} 接近涨停价{} 10个跳,不处理'.format(self.passive_vt_symbol, self.last_passive_tick.last_price,
                                                            self.last_passive_tick.limit_up))
                    self.cancel_algo()
                    self.stop()
                    return

                if 0 < self.last_active_tick.last_price - self.active_contract.pricetick * 10 < self.last_active_tick.limit_down:
                    self.write_log(
                        u'{}合约价格{} 接近跌停价{} 10个跳,不处理'.format(self.active_vt_symbol, self.last_active_tick.last_price,
                                                            self.last_active_tick.limit_down))
                    self.cancel_algo()
                    self.stop()
                    return

                if 0 < self.last_passive_tick.last_price + self.passive_contract.pricetick * 10 < self.last_passive_tick.limit_down:
                    self.write_log(
                        u'{}合约价格{} 接近跌停价{} 10个跳,不开仓'.format(self.passive_vt_symbol, self.last_passive_tick.last_price,
                                                            self.last_passive_tick.limit_down))
                    self.cancel_algo()
                    self.stop()
                    return

        # 如果有交易, 直接返回
        if self.entrust is True:
            return

        try:
            # 如果主动腿已经完成，则执行对冲
            if self.active_target_volume == self.active_traded_volume \
                    and self.passive_traded_volume != self.passive_target_volume:
                self.hedge()
                self.put_variables_event()
                return

            # 根据价差的bid/ask下单
            #  - 若买入方向限价单价格高于该价格，则会成交
            #  - 若卖出方向限价单价格低于该价格，则会成交

            update_var = False

            if self.order_command.lower() == 'buy':
                volume = self.active_target_volume - self.active_traded_volume
                self.write_log('{}.onTick({}), buy:{},askPrice1:{},bidPrice1:{},lastPrice:{},v:{}'
                               .format(self.algo_name, self.last_tick.vt_symbol, self.order_req_price,
                                       self.last_tick.ask_price_1, self.last_tick.bid_price_1,
                                       self.last_tick.last_price,
                                       volume))

                if self.last_tick.ask_price_1 <= self.order_req_price and self.last_active_tick.ask_volume_1 >= volume > 0:
                    ref = self.buy(
                        vt_symbol=self.active_vt_symbol,
                        price=self.last_active_tick.ask_price_1,
                        volume=volume,
                        offset=Offset.OPEN)
                    if len(ref) > 0:
                        self.active_orderID.extend(ref.split(';'))
                        self.active_orderID_history = self.active_orderID_history + '_'.join(
                            self.active_orderID) + '@' + str(
                            self.last_active_tick.ask_price_1) + ':'
                        update_var = True
                        self.entrust = True
                        self.count = 0

            elif self.order_command.lower() == 'sell':
                volume = self.active_target_volume - self.active_traded_volume
                self.write_log('{}.onTick({}), sell:{},askPrice:{},bidPrice1:{},lastPrice:{},v:{}'
                               .format(self.algo_name, self.last_tick.vt_symbol, self.order_req_price,
                                       self.last_tick.ask_price_1, self.last_tick.bid_price_1,
                                       self.last_tick.last_price,
                                       volume))

                if self.last_tick.bid_price_1 >= self.order_req_price and self.last_active_tick.bid_volume_1 >= volume > 0:
                    ref = self.sell(self.active_vt_symbol, self.last_active_tick.bid_price_1, volume,
                                    offset=Offset.CLOSE)
                    if len(ref) > 0:
                        self.active_orderID.extend(ref.split(';'))
                        self.active_orderID_history = self.active_orderID_history + u'{}'.format(
                            self.active_orderID) + '@' + str(
                            self.last_active_tick.bid_price_1) + ':'
                        update_var = True
                        self.entrust = True
                        self.count = 0

            elif self.order_command.lower() == 'short':
                volume = self.active_target_volume - self.active_traded_volume

                self.write_log('{}.onTick({}), short:{},askPrice:{},bidPrice1:{},lastPrice:{},v:{}'
                               .format(self.algo_name, self.last_tick.vt_symbol, self.order_req_price,
                                       self.last_tick.ask_price_1,
                                       self.last_tick.bid_price_1,
                                       self.last_tick.last_price, volume))

                if self.last_tick.bid_price_1 >= self.order_req_price and self.last_active_tick.bid_volume_1 >= volume > 0:
                    ref = self.sell(self.active_vt_symbol, self.last_active_tick.bid_price_1, volume,
                                    offset=Offset.OPEN)
                    if len(ref) > 0:
                        self.active_orderID.extend(ref.split(';'))
                        self.active_orderID_history = self.active_orderID_history + u'{}'.format(
                            self.active_orderID) + '@' + str(
                            self.last_active_tick.bid_price_1) + ':'
                        update_var = True
                        self.entrust = True
                        self.count = 0

            elif self.order_command.lower() == 'cover':
                volume = self.active_target_volume - self.active_traded_volume
                self.write_log('{}.onTick({}), cover:{},askPrice:{},bidPrice1:{},lastPrice:{},v:{}'
                               .format(self.algo_name, self.last_tick.vt_symbol, self.order_req_price,
                                       self.last_tick.ask_price_1,
                                       self.last_tick.bid_price_1,
                                       self.last_tick.last_price, volume))

                if self.last_tick.ask_price_1 <= self.order_req_price and self.last_active_tick.ask_volume_1 >= volume > 0:
                    ref = self.buy(self.active_vt_symbol, self.last_active_tick.ask_price_1, volume,
                                   offset=Offset.CLOSE)
                    if len(ref) > 0:
                        self.active_orderID = ref.split(';')
                        self.active_orderID_history = self.active_orderID_history + u'{}'.format(
                            self.active_orderID) + '@' + str(
                            self.last_active_tick.ask_price_1) + ':'
                        update_var = True
                        self.entrust = True
                        self.count = 0

            # 更新界面
            if update_var is True:
                self.put_variables_event()
        except Exception as e:
            self.write_error(u'onTick：{},{},{}'.format(self.strategy_name, str(e), traceback.format_exc()))

    def check_invest_money(self):
        """
        检查投资金额是否满足
        :return:
        """
        # 当前净值,可用资金,资金占用比例,资金上限
        balance, avaliable, occupy_percent, percent_limit = self.algo_engine.get_account()

        if occupy_percent >= percent_limit:
            self.write_log(u'当前资金占用:{},超过限定:{}'.format(occupy_percent, percent_limit))
            self.cancel_algo()
            self.stop()
            return False

        # 主动腿/被动腿得短合约符号
        activate_short_symbol = get_underlying_symbol(self.active_vt_symbol)
        passive_short_symbol = get_underlying_symbol(self.passive_vt_symbol)

        # 主动腿的合约size/保证金费率
        activate_size = self.algo_engine.get_size(self.active_vt_symbol)
        activate_margin_rate = self.algo_engine.get_margin_rate(self.active_vt_symbol)

        # 被动腿的合约size/保证金费率
        passive_size = self.algo_engine.get_size(self.passive_vt_symbol)
        passive_margin_rate = self.algo_engine.get_margin_rate(self.passive_vt_symbol)

        # 主动腿保证金/被动腿保证金
        activate_margin = self.active_target_volume * self.last_active_tick.last_price * activate_size * activate_margin_rate
        passive_margin = self.passive_target_volume * self.last_passive_tick.last_price * passive_size * passive_margin_rate

        if activate_short_symbol == passive_short_symbol:
            # 同一品种套利
            invest_margin = max(activate_margin, passive_margin)
        else:
            # 跨品种套利
            invest_margin = activate_margin + passive_margin

        # 计划使用保证金
        target_margin = balance * (occupy_percent / 100) + invest_margin

        if 100 * (target_margin / balance) > percent_limit:
            self.write_log(u'委托后,预计当前资金占用:{},超过限定:{}比例,不能开仓'
                           .format(100 * (target_margin / balance), percent_limit))
            self.cancel_algo()
            self.stop()
            return False

        return True

    def cancel_algo(self):
        """
        撤销当前算法实例订单
        :return:
        """
        self.write_log(u'{}发出算法撤单，合约:{}'.format(self.algo_name, self.order_vt_symbol))

        order = copy.copy(self.algo_order)
        order.status = Status.CANCELLED
        # 通用事件
        event1 = Event(type=EVENT_ORDER, data=order)
        self.algo_engine.event_engine.put(event1)

    def append_trade_record(self, trade):
        """
        添加交易记录到文件
        :param trade:
        :return:
        """
        trade_fields = ['datetime', 'symbol', 'exchange', 'vt_symbol', 'tradeid', 'vt_tradeid', 'orderid', 'vt_orderid',
                        'direction', 'offset', 'price', 'volume', 'idx_price']
        trade_dict = OrderedDict()
        try:
            for k in trade_fields:
                if k == 'datetime':
                    dt = getattr(trade, 'datetime')
                    if isinstance(dt, datetime):
                        trade_dict[k] = dt.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        trade_dict[k] = datetime.now().strftime('%Y-%m-%d') + ' ' + getattr(trade, 'time', '')
                if k in ['exchange', 'direction', 'offset']:
                    trade_dict[k] = getattr(trade, k).value
                else:
                    trade_dict[k] = getattr(trade, k, '')

            # 添加指数价格
            symbol = trade_dict.get('symbol')
            idx_symbol = get_underlying_symbol(symbol).upper() + '99.' + trade_dict.get('exchange')
            idx_price = self.algo_engine.get_price(self, idx_symbol)
            if idx_price:
                trade_dict.update({'idx_price': idx_price})
            else:
                trade_dict.update({'idx_price': trade_dict.get('price')})

            if self.strategy_name is not None:
                trade_file = os.path.abspath(
                    os.path.join(get_folder_path('data'), '{}_trade.csv'.format(self.strategy_name)))
                append_data(file_name=trade_file, dict_data=trade_dict)
        except Exception as ex:
            self.write_error(u'写入交易记录csv出错：{},{}'.format(str(ex), traceback.format_exc()))

    # ----------------------------------------------------------------------
    def on_trade(self, trade):
        """处理成交结果"""
        self.write_log('spreadAlgo.on_trade(), {}'.format(trade.__dict__))
        if trade.vt_symbol not in [self.active_vt_symbol, self.passive_vt_symbol]:
            self.write_log(u'不认识的交易：{},{}'.format(self.strategy_name, trade.vt_symbol))
            return

        # 如果是主动腿成交则需要执行对冲
        if trade.vt_symbol == self.active_vt_symbol:

            # 已经有交易了，不能停止
            if self.stopable:
                self.stopable = False

            self.active_traded_avg_price = trade.price * trade.volume + self.active_traded_avg_price * self.active_traded_volume
            self.active_traded_volume += trade.volume
            self.active_traded_avg_price /= self.active_traded_volume

            # 被动腿的已成交数量，与目标数量不一致
            if self.active_target_volume == self.active_traded_volume \
                    and self.passive_traded_volume != self.passive_target_volume \
                    and not self.entrust:
                self.hedge()

        else:
            self.passive_traded_avg_price = trade.price * trade.volume + self.passive_traded_avg_price * self.passive_traded_volume
            self.passive_traded_volume += trade.volume
            self.passive_traded_avg_price /= self.passive_traded_volume

        self.append_trade_record(trade)

        # 主动腿&被动腿都成交, 合成套利合约的成交更新事件, 并将它推送给EventEngine
        if self.passive_traded_volume == self.passive_target_volume and self.active_traded_volume == self.active_target_volume:
            traded_price = 0
            if self.is_spread:
                traded_price = self.active_traded_avg_price \
                               - self.passive_traded_avg_price
            elif self.is_ratio:
                traded_price = 100 * self.active_traded_avg_price * self.active_traded_volume \
                               / (self.passive_traded_avg_price * self.passive_traded_volume)
            self.write_log(u'所有交易已完成：{},{},ActiveOrderIDs:{},PassiveOrderIDs:{}'.format(self.strategy_name,
                                                                                        traded_price,
                                                                                        self.active_orderID_history,
                                                                                        self.passive_orderID_history))

            """套利合约的成交信息推送"""
            algo_trade = TradeData(
                gateway_name=self.gateway_name,
                symbol=self.order_symbol,
                exchange=self.exchange,
                orderid=self.algo_name,
                price=traded_price,
                volume=self.order_req_volume,
                tradeid=self.algo_name,
                sys_orderid=self.algo_name,
                time=trade.time,
                datetime=trade.datetime,
                strategy_name=self.strategy_name
            )

            if self.order_command.lower() == 'buy':
                algo_trade.direction = Direction.LONG
                algo_trade.offset = Offset.OPEN
            elif self.order_command.lower() == 'short':
                algo_trade.direction = Direction.SHORT
                algo_trade.offset = Offset.OPEN
            elif self.order_command.lower() == 'sell':
                algo_trade.direction = Direction.SHORT
                algo_trade.offset = Offset.CLOSE
            elif self.order_command.lower() == 'cover':
                algo_trade.direction = Direction.LONG
                algo_trade.offset = Offset.CLOSE

            # 通用事件
            event1 = Event(type=EVENT_TRADE, data=algo_trade)
            self.algo_engine.event_engine.put(event1)

            # 套利合约的订单变化推送
            order_price = 0
            if self.is_spread:
                order_price = self.active_order_avg_price \
                              - self.passive_order_avg_price
            elif self.is_ratio:
                order_price = 100 * self.active_order_avg_price * self.active_order_volume \
                              / (self.passive_order_avg_price * self.passive_order_volume)

            # 发送套利合约得onOrder事件
            algo_order = copy.copy(self.algo_order)
            algo_order.price = order_price
            algo_order.traded = algo_order.volume
            algo_order.status = Status.ALLTRADED

            # 通用事件
            event2 = Event(type=EVENT_ORDER, data=algo_order)
            self.algo_engine.event_engine.put(event2)

            self.stopable = True
            self.stop()

        self.put_variables_event()

    # ----------------------------------------------------------------------
    def on_order(self, order):
        """处理报单结果"""
        self.write_log('{}.on_order(), {}'.format(self.algo_name, order.__dict__))
        if order.vt_symbol not in [self.active_vt_symbol, self.passive_vt_symbol]:
            self.write_log(u'不认识的交易：{},{}'.format(self.strategy_name, order.vt_symbol))
            return

        if order.vt_symbol == self.active_vt_symbol:
            # 主动腿成交, 更新主动腿的平均成交价格
            if order.status == Status.ALLTRADED:
                old_orders = copy.copy(self.active_orderID)
                if order.vt_orderid not in self.active_orderID:
                    self.write_error(u'委托单：{}不在主动腿委托单列表中:{}'.format(order.vt_orderid, self.active_orderID))
                    return
                self.active_orderID.remove(order.vt_orderid)
                self.write_log(u'主动腿委托单号:{}=>{}'.format(old_orders, self.active_orderID))

                self.active_order_avg_price = order.price * order.volume + self.active_order_avg_price * self.active_order_volume
                self.active_order_volume += order.volume
                self.active_order_avg_price /= self.active_order_volume
                if len(self.active_orderID) == 0:
                    self.entrust = False
        elif order.vt_symbol == self.passive_vt_symbol:
            # 被动腿都成交, 更新被动腿的平均成交价格, 合成套利合约的报单更新事件, 并将它推送给EventEngine
            if order.status == Status.ALLTRADED:
                old_orders = copy.copy(self.passive_orderID)
                if order.vt_orderid not in self.passive_orderID:
                    self.write_error(u'委托单：{}不在被动腿委托单列表中:{}'.format(order.vt_orderid, self.passive_orderID))
                    return
                self.passive_orderID.remove(order.vt_orderid)
                self.write_log(u'被动腿委托单号:{}=>{}'.format(old_orders, self.passive_orderID))

                self.passive_order_avg_price = order.price * order.volume + self.passive_order_avg_price * self.passive_order_volume
                self.passive_order_volume += order.volume
                self.passive_order_avg_price /= self.passive_order_volume
                if len(self.passive_orderID) > 0:
                    return
                self.entrust = False

        self.put_variables_event()

    # ----------------------------------------------------------------------
    def on_timer(self):
        """定时检查, 未完成开仓，就撤单"""
        self.count += 1
        if self.count < self.timer_interval:
            return

        self.write_log('spreadAlgo.onTimer()')
        self.count = 0

        # Tick 未更新完毕
        if self.last_tick is None or self.last_passive_tick is None or self.last_active_tick is None:
            return

        try:
            # 撤单(主动腿/被动腿，均未开仓
            if len(self.active_orderID) == 0 and len(self.passive_orderID) == 0:
                self.write_log(u'{}超时撤单'.format(self.algo_name))
                self.cancel_all()
                self.entrust = False
                if len(self.passive_orderID) == 0:
                    self.cancel_algo()
                    self.stop()
                return

            # 更新界面
            self.put_variables_event()
        except Exception as e:
            self.write_error(u'onTimer exception：{},{},{}'.format(self.strategy_name, str(e), traceback.format_exc()))

    # ----------------------------------------------------------------------
    def on_stop(self):
        """"""
        self.write_log(u'算法停止')
        self.put_variables_event()

    # ----------------------------------------------------------------------
    def put_variables_event(self):
        """更新变量"""
        d = OrderedDict()
        d[u'算法状态'] = self.active
        d[u'运行计数'] = self.count
        d[u'主动腿持仓'] = self.active_traded_volume
        d[u'被动腿持仓'] = self.passive_traded_volume
        d[u'主动腿委托历史'] = self.active_orderID_history
        d[u'被动腿委托历史'] = self.passive_orderID_history
        self.algo_engine.put_variables_event(self, d)

    # ----------------------------------------------------------------------
    def put_parameters_event(self):
        """更新参数"""
        d = OrderedDict()
        d[u'价差合约'] = self.order_vt_symbol
        d[u'交易命令'] = self.order_command
        d[u'价差'] = self.order_req_price
        d[u'数量'] = self.order_req_volume
        d[u'间隔'] = self.timer_interval
        d[u'策略名称'] = self.strategy_name
        self.algo_engine.put_parameters_event(self, d)

    # ----------------------------------------------------------------------
    def hedge(self):
        """交易被动腿"""
        if self.stopable:
            self.stopable = False

        passive_tick = self.last_passive_tick

        if self.entrust:
            self.write_log(u'正在委托中，不能实施对冲交易')
            return

        min_diff = passive_tick.ask_price_1 - passive_tick.bid_price_1

        if self.order_command.lower() == 'buy':
            volume = self.passive_target_volume - self.passive_traded_volume
            if volume > 0:
                trade_price = max(passive_tick.bid_price_1 - min_diff, passive_tick.limit_down)
                self.write_log('{}.hedge(), buy'.format(self.algo_name))
                ref = self.sell(self.passive_vt_symbol, trade_price, volume, offset=Offset.OPEN)
                if len(ref) > 0:
                    self.passive_orderID.extend(ref.split(';'))
                    self.passive_orderID_history = self.passive_orderID_history + '_'.join(
                        self.passive_orderID) + '@' + str(trade_price) + ':'
                    self.entrust = True
                    self.count = 0
        elif self.order_command.lower() == 'sell':
            volume = self.passive_target_volume - self.passive_traded_volume
            if volume > 0:
                trade_price = min(passive_tick.ask_price_1 + min_diff, passive_tick.limit_up)
                self.write_log('{}.hedge(), sell'.format(self.algo_name))
                ref = self.buy(self.passive_vt_symbol, trade_price, volume, offset=Offset.CLOSE)
                if len(ref) > 0:
                    self.passive_orderID.extend(ref.split(';'))
                    self.passive_orderID_history = self.passive_orderID_history + '_'.join(
                        self.passive_orderID) + '@' + str(trade_price) + ':'
                    self.entrust = True
                    self.count = 0
        elif self.order_command.lower() == 'short':
            volume = self.passive_target_volume - self.passive_traded_volume
            if volume > 0:
                trade_price = min(passive_tick.ask_price_1 + min_diff, passive_tick.limit_up)
                self.write_log('{}.hedge(), short'.format(self.algo_name))
                ref = self.buy(self.passive_vt_symbol, trade_price, volume, offset=Offset.OPEN)
                if len(ref) > 0:
                    self.passive_orderID.extend(ref.split(';'))
                    self.passive_orderID_history = self.passive_orderID_history + '_'.join(
                        self.passive_orderID) + '@' + str(trade_price) + ':'
                    self.entrust = True
                    self.count = 0
        elif self.order_command.lower() == 'cover':
            volume = self.passive_target_volume - self.passive_traded_volume
            if volume > 0:
                trade_price = max(passive_tick.bid_price_1 - min_diff, passive_tick.limit_down)
                self.write_log('{}.hedge(), cover'.format(self.algo_name))
                ref = self.sell(self.passive_vt_symbol, trade_price, volume, offset=Offset.CLOSE)
                if len(ref) > 0:
                    self.passive_orderID.extend(ref.split(';'))
                    self.passive_orderID_history = self.passive_orderID_history + '_'.join(
                        self.passive_orderID) + '@' + str(trade_price) + ':'
                    self.entrust = True
                    self.count = 0
