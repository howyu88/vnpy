# encoding: utf-8

# 该文件，为无界面调度文件，以vtClient为基准，
# 通过vt_setting访问远程RPC server端口，进行指令调度
# runDispatchClient.py 指令 + 参数/参数文件

import sys
import os
import traceback
import json
from pick import pick
from vnpy.rpc import RpcClient

from vnpy.trader.utility import load_json


class DispatchClient(RpcClient):

    def __init__(self, name):
        super().__init__()
        self.name = name

    def callback(self, topic, data):
        """
        Realize callable function
        """
        pass
        #print(f"client received topic:{topic}, data:{data}")

    def status(self):
        if self.__active:
            return u'connected:[{}]'.format(self.name)
        else:
            return u'No connect'
    @property
    def connected(self):
        return self.__active

def run_dispatch_client():

    ds_client: DispatchClient = None

    config = load_json('dispatch_client.json', auto_save=False)

    # 主菜单
    main_title = u'Rpc Client'
    main_options = ['Connect', 'Disconnect', '[GW] Status', '[Strategy] Get Running', '[Strategy] Compare Pos',
                    '[Strategy] Add', '[Strategy] Init',
                    '[Strategy] Start', '[Strategy] Stop', '[Strategy] Reload', '[Strategy] Remove',
                    '[Strategy] Save Data', '[Strategy] Save Snapshot', 'Exit']
    option = None
    strategies = ['back']
    gateways = []

    def get_strategies():
        """获取策略清单/状态"""
        if ds_client is None:
            return []
        if not ds_client.connected:
            return []
        all_strategy_status = ds_client.get_strategy_status()
        if isinstance(all_strategy_status, dict):
            strategy_names = sorted(all_strategy_status.keys())
            for name in strategy_names:
                print(u'{}:{}'.format(name, all_strategy_status.get(name)))
            return strategy_names + ['back']
        else:
            return []

    def get_all_gateway_status():
        """获取网关清单/状态"""
        if ds_client is None:
            return []
        if not ds_client.connected:
            return []

        all_gateway_status = ds_client.get_all_gateway_status()
        return all_gateway_status

    def get_status():
        """查询远程状态"""
        if ds_client is None:
            return ''
        else:
            return ds_client.status()

    def get_local_json_file_names():
        """ 获取本地json文件清单"""
        print('get local json files:'.format(os.getcwd()))
        file_names = []
        for dirpath, dirnames, filenames in os.walk(os.getcwd()):
            for filename in filenames:
                if filename.endswith(".json"):
                    file_names.append(filename)
                else:
                    continue

        return sorted(file_names)

    def add_strategies(file_name):
        """从本地Json文件添加策略"""
        settings = load_json(file_name, auto_save=False)
        if not isinstance(settings, dict):
            print(f'{file_name} is not a dict format')
            return

        for strategy_name, strategy_conf in settings.items():
            if strategy_name in strategies:
                print(f'{strategy_name} already exist in runing list, can not add', file=sys.stderr)
                continue
            if 'class_name' not in strategy_conf:
                continue
            if 'vt_symbol' not in strategy_conf:
                continue
            if 'setting' not in strategy_conf:
                continue

            ret, msg = ds_client.add_strategy(
                class_name=strategy_conf.get('class_name'),
                strategy_name=strategy_name,
                vt_symbol=strategy_conf.get('vt_symbol'),
                setting=strategy_conf.get('setting'),
                auto_init=strategy_conf.get('auto_init', True),
                auto_start=strategy_conf.get('auto_start', True)
            )
            if ret:
                print(msg)
            else:
                print(msg, file=sys.stderr)


    while (1):
        if option is None:
            option, index = pick(main_options, main_title + get_status())

            # 退出
            if option == 'Exit':
                if ds_client and ds_client.connected:
                    ds_client.close()
                print(u'Good bye\n')
                os._exit(0)
                break

            # 连接远程服务
            elif option == 'Connect':
                if ds_client:
                    print(u'{}，please disconnect first'.format(ds_client.status()))
                else:
                    title = u'Select the Server to connect'
                    server_list = sorted(config.keys())
                    server, index = pick(server_list, title)

                    if server:
                        conf = config.get(server)
                        ds_client = DispatchClient(server)
                        print(conf)
                        ds_client.start(
                            req_address=conf.get('req_address'),
                            sub_address=conf.get('pub_address')
                        )
                        strategies = get_strategies()
                        if len(strategies) == 0:
                            print('no strategies running')

            # 断开远程服务
            elif option == 'Disconnect':
                if ds_client.connected:
                    ds_client.close()

            # 查询Gateway状态服务
            elif option == '[GW] Status':
                gateways = get_all_gateway_status()
                s = json.dumps(gateways, indent=-1)
                print(s)
            elif option == '[GW] Connect':
                gateways = get_all_gateway_status()
                un_connect_gateway_name = [k for k, v in gateways if not v.get('con', False)]
                selected = pick(options=sorted(un_connect_gateway_name), title='Please select gateway to connect Enter',
                                multi_select=False)
            # 查询策略
            elif option == '[Strategy] Get Running':
                if not ds_client or not ds_client.connected:
                    print(u'{}，please connect first'.format(get_status()))
                else:
                    strategies = get_strategies()
            # 添加策略
            elif option == '[Strategy] Add':
                if not ds_client or not ds_client.connected:
                    print(u'{}，please connect first'.format(get_status()))
                else:
                    json_files = get_local_json_file_names()
                    if len(json_files) == 0:
                        print('no json file to load')
                    else:
                        json_files.append('back')
                        selected = pick(
                            options=sorted(json_files),
                            title='Please select settings to add,press Enter',
                            multi_select=True)
                        for file_name, index in selected:
                            if file_name != 'back':
                                add_strategies(file_name)

                        strategies = get_strategies()

            # 停止策略
            elif option == '[Strategy] Stop':
                if not ds_client or not ds_client.connected:
                    print(u'{}，please connect first'.format(get_status()))
                else:
                    selected = pick(options=sorted(strategies), title='Please select strategy to stop,press Enter',
                                    multi_select=True)
                    for strategy_name, index in selected:
                        if strategy_name != 'back':
                            print('start stopping :{}\n'.format(strategy_name))
                            ret = ds_client.stop_strategy(strategy_name)
                            if ret:
                                print('stop success')
                            else:
                                print('stop fail')
            # 启动策略
            elif option == '[Strategy] Start':
                if not ds_client or not ds_client.connected:
                    print(u'{}，please connect first'.format(get_status()))
                else:
                    selected = pick(options=sorted(strategies),
                                    title='Please use Space select multi strategies to start.press Enter',
                                    multi_select=True)
                    for strategy_name, index in selected:
                        if strategy_name != 'back':
                            print('start starting :{}\n'.format(strategy_name))
                            ret = ds_client.rpc_client.start_strategy(strategy_name)
                            if ret:
                                print('start success')
                            else:
                                print('start fail')

            # 重新加载策略
            elif option == '[Strategy] Reload':
                if not ds_client or not ds_client.connected:
                    print(u'{}，please connect first'.format(get_status()))
                else:
                    selected = pick(options=sorted(strategies),
                                    title='Please use Space select multi strategies to reload.press Enter',
                                    multi_select=True)
                    for strategy_name, index in selected:
                        if strategy_name != 'back':
                            print('start reloading :{}\n'.format(strategy_name))
                            ret, msg = ds_client.reload_strategy(strategy_name)
                            if ret:
                                print(msg)
                            else:
                                print(msg, file=sys.stderr)

            # 移除策略
            elif option == '[Strategy] Remove':
                if not ds_client or not ds_client.connected:
                    print(u'{}，please connect first'.format(get_status()))
                else:
                    has_changed = False
                    selected = pick(options=sorted(strategies),
                                    title='Please use Space select strategy to dispatch out.press Enter',
                                    multi_select=True)
                    for strategy_name, index in selected:
                        if strategy_name != 'back':
                            print('start dispatching out :{}\n'.format(strategy_name))
                            ret, msg = ds_client.remove_strategy(strategy_name)
                            if ret:
                                print(msg)
                                has_changed = True
                            else:
                                print(msg, file=sys.stderr)

                    if has_changed:
                        strategies = get_strategies()
            # 保存策略数据
            elif option == '[Strategy] Save Data':
                if not ds_client or not ds_client.connected:
                    print(u'{}，please connect first'.format(get_status()))
                else:
                    has_changed = False

                    selected = pick(options=['ALL'] + sorted(strategies),
                                    title='Please use Space select strategy to save data.press Enter',
                                    multi_select=True)
                    if 'ALL' in selected and len(selected) > 1:
                        selected = ['ALL']
                    for strategy_name, index in selected:
                        if strategy_name != 'back':
                            print('start save :{}\n'.format(strategy_name))
                            ret, msg = ds_client.save_strategy_data(strategy_name)
                            if ret:
                                print(msg)
                                has_changed = True
                            else:
                                print(msg, file=sys.stderr)

                    if has_changed:
                        strategies = get_strategies()
            # 保存策略bars切片数据
            elif option == '[Strategy] Save Snapshot':
                if not ds_client or not ds_client.connected:
                    print(u'{}，please connect first'.format(get_status()))
                else:
                    has_changed = False

                    selected = pick(options=['ALL'] + sorted(strategies),
                                    title='Please use Space select strategy to save bars snapshot.press Enter',
                                    multi_select=True)
                    if 'ALL' in selected and len(selected) > 1:
                        selected = ['ALL']
                    for strategy_name, index in selected:
                        if strategy_name != 'back':
                            print('start save bars snapshot :{}\n'.format(strategy_name))
                            ret, msg = ds_client.save_strategy_snapshot(strategy_name)
                            if ret:
                                print(msg)
                                has_changed = True
                            else:
                                print(msg, file=sys.stderr)

                    if has_changed:
                        strategies = get_strategies()
            # 比对仓位
            elif option == '[Strategy] Compare Pos':
                if not ds_client or not ds_client.connected:
                    print(u'{}，please connect first'.format(get_status()))
                else:
                    ret, msg = ds_client.compare_pos()
                    if ret:
                        print(msg)
                    else:
                        print(msg, file=sys.stderr)

            _input = input('press any key')
            option = None
            continue
