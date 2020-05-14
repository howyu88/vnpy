# encoding: utf-8

# 该文件，为无界面调度文件，以vtClient为基准，
# 通过vt_setting访问远程RPC server端口，进行指令调度
# runDispatchClient.py 指令 + 参数/参数文件

import sys, os
import traceback
ROOT_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
if ROOT_PATH not in sys.path:
    print(f'append {ROOT_PATH} into sys.path')
    sys.path.append(ROOT_PATH)

from vnpy.app.dispatch.dispatch_client import run_dispatch_client

if __name__ == '__main__':
    run_dispatch_client()
