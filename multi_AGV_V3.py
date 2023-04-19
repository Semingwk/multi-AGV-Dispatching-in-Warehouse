'''
# 多AGV场景模拟 
# 循环遍历，并行计算
# 使用action buffer输出内容，内容是按照时序排列的
'''
import numpy as np
import threading
import time
import random

class AGV:
    # AGV属性：id，物料编号，托盘编号，电量
    def __init__(self):
        self.id = None
        self.part = None      # AGV上的物料
        self.tray = None      # AGV上的托盘
        self.elec = 100       # AGV电量

class SA_region:
    def __init__(self, num_AGV_1, num_AGV_2, N_parts_A, N_parts_B):
        self.tray_count = 0      # 计算SA回收托盘的数量
        self.reserve_count = 0   # 预计前往SA拿物料的AGV个数，用于预估时间
        self.part_count = 0      # 计算SA取走物料的数量，用于预估时间
        self.total_part_num = N_parts_A
        self.parts_SA = [N_parts_B+i+1 for i in range(N_parts_A)]     # 初始化上料口SA待处理的所有物料
        self.SA_tray = [num_AGV_1+i+1 for i in range(num_AGV_2)]     # 初始化上料口SA所有托盘，托盘数量与该区域AGV数量相同
    
    def check_reserve_full(self):
        if self.part_count+self.reserve_count >= self.total_part_num or len(self.SA_tray) < 1:
            return True
        else:
            return False
        
    def reserve(self):
        self.reserve_count += 1
    
    def cancel_reserve(self):
        self.reserve_count -= 1

class SB_region:
    def __init__(self, num_AGV_1, N_parts_B):
        self.tray_count = 0
        self.reserve_count = 0
        self.part_count = 0
        self.total_part_num = N_parts_B
        self.parts_SB = [i+1 for i in range(N_parts_B)]     # 初始化上料口SB待处理的所有物料
        self.SB_tray = [i+1 for i in range(num_AGV_1)]     # 初始化上料口SB所有托盘，托盘数量与该区域AGV数量相同

    def check_reserve_full(self):
        if self.part_count+self.reserve_count == self.total_part_num:
            return True
        else:
            return False
    
    def reserve(self):
        self.reserve_count += 1
    
    def cancel_reserve(self):
        self.reserve_count -= 1

class General_Location:
    # 普通属性：被占用列表，最大占用数量，flag是否已满
    def __init__(self, max_loc_num):
        self.oc_list = []
        self.max_oc_num = max_loc_num
        self.reserve_num = 0
        self.reserve_pos_occupy_num = 0
    
    # 预约前往放置物料/托盘
    def reserve_position(self):
        self.reserve_num += 1
        self.reserve_pos_occupy_num = len(self.oc_list) + self.reserve_num
    
    # 放好物料/托盘后，取消预约，改为占据
    def cancel_reserve_after_reach(self):
        self.reserve_num -= 1
        self.reserve_pos_occupy_num = len(self.oc_list) + self.reserve_num
    
    # 检查是否已经预约+占据满，用于flag刷新
    def check_full(self):
        assert self.reserve_pos_occupy_num <= self.max_oc_num, 'Region position out of range! Check!'
        if self.reserve_pos_occupy_num == self.max_oc_num:
            return True
        else:
            return False  

    def check_empty(self):
        if len(self.oc_list) == 0:
            return True
        else:
            return False 

class Process_Location(General_Location):
    # 继承普通General_Location的加工区属性：物料占用后的剩余待处理时间，托盘管理
    def __init__(self, max_loc_num):
        super(Process_Location, self).__init__(max_loc_num = max_loc_num)
        self.rt_list = []
        self.tray_list = []
        self.reserve_tray_num = 0

    # 预约前往拿走托盘
    def reserve_take_trayorpart(self):
        self.reserve_tray_num += 1

    # 拿走托盘后预约数量-1
    def cancel_reserve_after_take(self):
        self.reserve_tray_num -= 1

    # 计算等待时间（被预约m个托盘后，就要计算第m个好的托盘等待时间）
    def waiting_time_calculate(self):
        rt_list_copy = self.rt_list.copy()
        rt_list_copy.sort()
        return self.rt_list[self.rt_list.index(rt_list_copy[self.reserve_tray_num-1])]
        
    # 如果预约的数量已经超过了在处理的数量，则不能在前往
    def check_reserve_trayorpart_full(self):
        if self.reserve_tray_num >= len(self.tray_list):
            return True
        else:
            return False
    
class Cash_Location(General_Location):
    # 继承普通General_Location的缓存属性：托盘管理
    def __init__(self, max_loc_num):
        super(Cash_Location, self).__init__(max_loc_num = max_loc_num)
        self.tray_list = []    # 单独托盘则oc_list append None
        self.reserve_tray_num = 0

    # 预约前往拿走托盘/物料
    def reserve_take_trayorpart(self):
        self.reserve_tray_num += 1

    # 拿走托盘后预约数量-1
    def cancel_reserve_after_take(self):
        self.reserve_tray_num -= 1

    # 如果预约的数量已经超过了占据的物料/托盘数量，则不能在前往
    def check_reserve_trayorpart_full(self):
        if self.reserve_tray_num > len(self.oc_list):
            return True
        else:
            return False

class Lifting_Location:   
    def __init__(self, max_loc_num):
        self.oc_list = []
        self.max_oc_num = max_loc_num
        self.reserve_num = 0
        self.reserve_pos_occupy_num = 0
        # 放入物料/托盘的位置，是否available
        self.in_pos_available = [True, True]
        # 取走物料/托盘的位置，是否available
        self.out_pos_available = [False, False]
        # 四个位置的等待时间
        self.rt_list_in = [0, 0]
        self.rt_list_out = [5e10, 5e10]
        self.tray_list = []
        self.reserve_tray_num = 0
        self.t_D  = 100
        self.initialize()
    
    # 预约前往放置物料/托盘
    def reserve_position(self):
        self.reserve_num += 1
        oc_len = [i for i, x in enumerate(self.oc_list) if x != None]
        self.reserve_pos_occupy_num = len(oc_len) + self.reserve_num
    
    # 放好物料/托盘后，取消预约，改为占据
    def cancel_reserve_after_reach(self):
        self.reserve_num -= 1
        oc_len = [i for i, x in enumerate(self.oc_list) if x != None]
        self.reserve_pos_occupy_num = len(oc_len) + self.reserve_num
    
    # 检查是否已经预约+占据满，用于flag刷新
    def check_full(self):
        idx = [i for i, x in enumerate(self.oc_list) if x == None and self.in_pos_available[i] == True]
        if self.reserve_num >= len(idx):
            return True
        else:
            return False


    def check_empty(self):
        if len(self.oc_list) == 0:
            return True
        else:
            return False 
    
    def initialize(self):
        self.tray_list = [None, None]
        self.oc_list = [None, None]

    def check_in_pos_available(self):
        idx = [i for i, x in enumerate(self.in_pos_available) if x == True]
        if len(idx) > 0:
            return True
        else:
            return False
         
    def check_out_pos_available(self):
        idx = [i for i, x in enumerate(self.out_pos_available) if x == True]
        if len(idx) > 0:
            return True
        else:
            return False
    
    def return_put_partortray_pos(self):
        idx = [i for i, x in enumerate(self.in_pos_available) if x == True]
        if len(idx) == 1:
            return idx[0]
        elif len(idx) == 2:
            if self.rt_list_in[idx[0]] <= self.rt_list_in[idx[1]]:
                return idx[0]
            else:
                return idx[1]
        else:
            print("No valid position in D, pleas check")
    
    def return_take_partortray_pos(self):
        # print(self.out_pos_available)
        idx = [i for i, x in enumerate(self.out_pos_available) if x == True]
        if len(idx) == 1:
            return idx[0]
        elif len(idx) == 2:
            if self.rt_list_out[idx[0]] <= self.rt_list_out[idx[1]]:
                return idx[0]
            else:
                return idx[1]
        else:
            print("No valid position in D, pleas check")
    
    def return_take_waiting_time(self):
        index = self.return_take_partortray_pos()
        return self.rt_list_out[index]
    
    def return_put_waiting_time(self):
        index = self.return_put_partortray_pos()
        return self.rt_list_in[index]

    def put_partortray(self, part, tray, time, idx):
        self.oc_list[idx] = part
        self.tray_list[idx] = tray
        self.rt_list_in[idx] = 5e10
        self.rt_list_out[idx] = time + self.t_D
        self.in_pos_available[idx] = False
        self.out_pos_available[idx] = True
        self.cancel_reserve_after_reach()

    def take_partortray(self, idx, time):
        part = self.oc_list[idx]
        tray = self.tray_list[idx]
        self.oc_list[idx] = None
        self.tray_list[idx] = None
        self.rt_list_out[idx] = 5e10
        self.rt_list_in[idx] = self.t_D + time
        self.in_pos_available[idx] = True
        self.out_pos_available[idx] = False
        self.cancel_reserve_after_take()
        return part, tray
    
    # 预约前往拿走托盘/物料
    def reserve_take_trayorpart(self):
        self.reserve_tray_num += 1

    # 拿走托盘后预约数量-1
    def cancel_reserve_after_take(self):
        self.reserve_tray_num -= 1

    # 如果预约的数量已经超过了占据的物料/托盘数量，则不能在前往
    def check_reserve_trayorpart_full(self):
        idx = [i for i, x in enumerate(self.tray_list) if x != None and self.out_pos_available[i] == True]
        # print(self.tray_list)
        # print(self.out_pos_available)
        # print(self.reserve_tray_num)
        if self.reserve_tray_num >= len(idx):
            return True
        else:
            return False




class ProductionWorld:
    def __init__(self):
        self.N_parts_SA = 20   # 上料口A一共N个物料
        self.N_parts_SB = 20   # 上料口B一共N个物料
        self.part_freq = 55   # 每隔55秒上料口出现一个物料
        self.t_SA_PA = 300    # 上料口SA到加工区PA的AGV运行时间
        self.t_PA_SA = 300    # 上料口SA到加工区PA的AGV运行时间
        self.t_SA_PB= 350     # 上料口SA到加工区PB的AGV运行时间
        self.t_SA_C = 200     # 上料口SA到缓存区C的AGV运行时间
        self.t_SA_D = 150     # 上料口SA到缓存区C的AGV运行时间
        self.t_D_SA = 150     # 上料口SA到缓存区C的AGV运行时间
        self.t_C_PA = 100     # 缓存区C到加工区PA的AGV运行时间
        self.t_PA_C = 100     # 缓存区C到加工区PA的AGV运行时间
        self.t_C_PB = 100     # 缓存区C到加工区PB的AGV运行时间
        self.t_PB_C = 100
        self.t_C_D = 50       # 提升机D到缓存区C的AGV运行时间
        self.t_D_C = 50       # 提升机D到缓存区C的AGV运行时间
        self.t_D_PB = 150     # 提升机D到加工区PB的AGV运行时间
        self.t_PB_D = 150
        self.t_D_PA = 200     # 提升机D到加工区PA的AGV运行时间
        self.t_PA_D = 200    
        self.t_SB_D = 150     # 上料口B提升机D的AGV运行时间
        self.t_PA_PB = 50     # 加工区PB到加工区PA的AGV运行时间
        self.t_PB_PA = 50     
        self.t_P = 1800       # 物料在加工区的加工时间
        self.t_D  = 100       # 物料和托盘在提升机的运行时间
        self.num_AGV_1 = 4    # 一层的AGV数量
        self.num_AGV_2 = 15    # 二层的AGV数量
        self.AGV_1 = []       # 一层AGV列表
        self.AGV_2 = []       # 二层AGV列表
        self.t_SA_E2 = 150    # 上料口SA到缓存区C的AGV运行时间
        self.t_D_E2 = 150     # 提升机D到充电区E2的AGV运行时间
        self.t_C_E2 = 50      # 缓存区C到充电区E2的AGV运行时间
        self.t_PA_E2 = 100    # 加工区PA到充电区E2的AGV运行时间
        self.t_PB_E2 = 200    # 加工区PB到充电区E2的AGV运行时间
        self.t_SB_E1 = 150    # 上料口SB到充电区E1的AGV运行时间
        self.t_D_E1 = 150     # 提升机D到充电区E1的AGV运行时间
        self.elec_consume_empty = 0.02            # AGV空载耗电速度
        self.elec_consume_withpart = 0.04         # AGV负载耗电速度
        self.elec_charge_speed = 0.05             # AGV充电速度
        

        self.node_list = ['SA', 'SB', 'PA', 'PB', 'C', 'D', 'E1', 'E2']  # 所有需要经过的节点
        self.waiting_list_1 = [None for i in range(self.num_AGV_1)]    # 表示区域一AGV是否需要等待
        self.waiting_list_2 = [None for i in range(self.num_AGV_2)]    # 表示区域二AGV是否需要等待
        self.time_queue = []    # 时间序列
        self.agv_action_buffer = {} # agv_action_buffer[time] = {'Location':(1,2)哪个区域第几辆AGV, 'node': 'SB', 'action':'要输出的内容'}
        self.node_1 = 'SB'
        self.node_2 = 'SA'

        
        self.finish_parts_PA = [self.N_parts_SB+i+1 for i in range(self.N_parts_SA)]     # 上料口SA待处理的所有物料全部运到加工区PA
        self.finish_parts_PB = [i+1 for i in range(self.N_parts_SB)]     # 上料口SB待处理的所有物料全部运到加工区PB
        self.SA_condition = SA_region(self.num_AGV_1, self.num_AGV_2, self.N_parts_SA, self.N_parts_SB)
        self.SB_condition = SB_region(self.num_AGV_1, self.N_parts_SB)
        self.PA_condition = Process_Location(5)         # 初始化加工区PA的信息
        self.PB_condition = Process_Location(5)         # 初始化加工区PB的信息
        self.C_condition = Cash_Location(10)         # 初始化缓存区C的信息
        self.D_in_condition = Lifting_Location(2)       # 初始化提升机D物料入/出口的信息
        self.D_out_condition = Lifting_Location(2)      # 初始化提升机D托盘出/入口的信息
        self.E1 = General_Location(1)                   # 初始化充电区E1的信息
        self.E2 = General_Location(6)                   # 初始化充电区E2的信息
        self.total_time_recorder = np.zeros((2, max(self.num_AGV_1, self.num_AGV_2)))  # 维护各个AGV的经历总时间
        self.init_AGV()                                 # 初始化所有的AGV
        # 初始化reward_function超参数
        self.t_fac = 0.01
        self.s_fac = 0.01
        self.put_part1 = 5
        self.put_part2 = 3
        self.take_part = 1
        self.minus_inf = -5e10

    # 初始化所有的AGV
    def init_AGV(self):
        for i in range(self.num_AGV_1):
            self.AGV_1.append(AGV())
            self.AGV_1[i].id = i+1
        for i in range(self.num_AGV_2):
            self.AGV_2.append(AGV())
            self.AGV_2[i].id = i+1
    
    # 检查是否已经完成所有工序
    def check_finish(self):
        # 上料口SA, SB物料都被运走
        # 且物料都被运到加工区PA, PB
        # 且
        if len(self.SA_condition.parts_SA) == 0 and len(self.SB_condition.parts_SB) == 0 and len(self.finish_parts_PA) == 0 and len(self.finish_parts_PB) == 0 \
             and self.SA_condition.tray_count == self.N_parts_SA and self.SB_condition.tray_count == self.N_parts_SB:
            print('AGV has finished transporting all of the parts and returning all the trays. Total time consumption is {}s.'.format(self.total_time_recorder.max()))
            return True
        else:
            return False
    
    def central_control(self, time_elapsed, no_pair, is_waiting=False):
        if not is_waiting:
            self.total_time_recorder[no_pair[0]-1, no_pair[1]-1] += time_elapsed
        else:
            self.total_time_recorder[no_pair[0]-1, no_pair[1]-1] = max(self.total_time_recorder[no_pair[0]-1, no_pair[1]-1], self.total_time_recorder[no_pair[0]-1, :].max()) # 
    
    ##############################################################################
    # 区域二AGV运动函数
    ##############################################################################
    
    ## 区域二AGV从上料口SA拿起一个物料和托盘，前往加工区PA/缓存区C
    # 输入：小车编号，下一个要去的结点
    def AGV_wait_and_carry_partAndtray_from_SA(self, instance_no, node):
        if self.SA_condition.part_count == 0:
            self.AGV_2[instance_no-1].part = self.SA_condition.parts_SA.pop(0)
            self.AGV_2[instance_no-1].tray = self.SA_condition.SA_tray.pop(0)
            self.SA_condition.part_count += 1
        elif self.total_time_recorder[1,instance_no-1] >= self.SA_condition.part_count*self.part_freq:
            self.AGV_2[instance_no-1].part = self.SA_condition.parts_SA.pop(0)
            self.AGV_2[instance_no-1].tray = self.SA_condition.SA_tray.pop(0)
            self.SA_condition.part_count += 1
        else:
            self.central_control(self.SA_condition.part_count*self.part_freq-self.total_time_recorder[1,instance_no-1], (2, instance_no))
            self.AGV_2[instance_no-1].part = self.SA_condition.parts_SA.pop(0)
            self.AGV_2[instance_no-1].tray = self.SA_condition.SA_tray.pop(0)
            self.SA_condition.part_count += 1
            # print("No part in SA before, AGV_2_{} is waiting, time{}\n".format(instance_no-1, self.total_time_recorder[1,instance_no-1]))
        if node == 'PA':
            self.central_control(self.t_SA_PA, (2, instance_no))
            self.AGV_2[instance_no-1].elec -= self.t_SA_PA*self.elec_consume_withpart
            self.PA_condition.reserve_position()
        elif node == 'C':
            self.central_control(self.t_SA_C, (2, instance_no))
            self.AGV_2[instance_no-1].elec -= self.t_SA_C*self.elec_consume_withpart
            self.C_condition.reserve_position()
        else:
            print("wrong location given")
        self.total_time_recorder[1,instance_no-1], self.time_queue = self.time_correction(self.time_queue, self.total_time_recorder[1,instance_no-1])
        time = self.total_time_recorder[1,instance_no-1]
        self.agv_action_buffer[time] = {'location':(2,instance_no), 'node': node, 'action':"AGV_2_{} is going from SA to {} with part {} with tray {}, elec {}, time{}\n".format(instance_no-1, node, self.AGV_2[instance_no-1].part, \
            self.AGV_2[instance_no-1].tray, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1])}
        # print("AGV_2_{} is going from SA to {} with part {} with tray {}, elec {}, time{}\n".format(instance_no-1, node, self.AGV_2[instance_no-1].part, \
        #     self.AGV_2[instance_no-1].tray, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1]))

    ## 区域二AGV从缓存区C拿起一个物料和托盘，前往加工区PA/PB
    def AGV_carry_partAndtray_from_C(self, instance_no, id, node):
        self.C_condition.cancel_reserve_after_take()
        part = self.C_condition.oc_list.pop(id)
        tray = self.C_condition.tray_list.pop(id)
        self.AGV_2[instance_no-1].part = part
        self.AGV_2[instance_no-1].tray = tray
        if node == 'PA':
            self.PA_condition.reserve_position()
            self.central_control(self.t_C_PA, (2, instance_no))
            self.AGV_2[instance_no-1].elec -= self.t_C_PA*self.elec_consume_withpart
        elif node == 'PB':
            self.PB_condition.reserve_position()
            self.central_control(self.t_C_PB, (2, instance_no))
            self.AGV_2[instance_no-1].elec -= self.t_C_PB*self.elec_consume_withpart
        else:
            print("wrong location given")
        self.total_time_recorder[1,instance_no-1], self.time_queue = self.time_correction(self.time_queue, self.total_time_recorder[1,instance_no-1])
        time = self.total_time_recorder[1,instance_no-1]
        self.agv_action_buffer[time] = {'location':(2,instance_no), 'node': node, 'action': "AGV_2_{} is going from C to {} with part {} with tray {}, elec {}, time{}\n".format(instance_no-1, node, self.AGV_2[instance_no-1].part, \
            self.AGV_2[instance_no-1].tray, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1])}
        # print("AGV_2_{} is going from C to {} with part {} with tray {}, elec {}, time{}\n".format(instance_no-1, node, self.AGV_2[instance_no-1].part, \
        #     self.AGV_2[instance_no-1].tray, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1]))

    ## 区域二AGV从提升机D拿起一个物料和托盘，前往缓存区C/PB
    def AGV_carry_partAndtray_from_D(self, instance_no, node):
        # print(self.D_in_condition.oc_list)
        # print(self.D_in_condition.tray_list)
        # print(self.D_in_condition.rt_list_in)
        # print(self.D_in_condition.rt_list_out)
        idx = self.D_in_condition.return_take_partortray_pos()
        waiting = self.D_in_condition.return_take_waiting_time()
        # print(idx)
        # print(waiting)
        self.central_control(max(0, waiting - self.total_time_recorder[1,instance_no-1]), (2, instance_no))
        part, tray = self.D_in_condition.take_partortray(idx, self.total_time_recorder[1,instance_no-1])
        self.AGV_2[instance_no-1].part = part
        self.AGV_2[instance_no-1].tray = tray
        if node == 'C':
            self.central_control(self.t_C_D, (2, instance_no))
            self.AGV_2[instance_no-1].elec -= self.t_C_D*self.elec_consume_withpart
            self.C_condition.reserve_position()
        elif node == 'PB':
            self.central_control(self.t_D_PB, (2, instance_no))
            self.AGV_2[instance_no-1].elec -= self.t_D_PB*self.elec_consume_withpart
            self.PB_condition.reserve_position
        else:
            print("wrong location given")
        self.total_time_recorder[1,instance_no-1], self.time_queue = self.time_correction(self.time_queue, self.total_time_recorder[1,instance_no-1])
        time = self.total_time_recorder[1,instance_no-1]
        self.agv_action_buffer[time] = {'location':(2,instance_no), 'node': node, 'action': "AGV_2_{} is going from D to {} with part {} with tray {}, elec {}, time{}\n".format(instance_no-1, node, self.AGV_2[instance_no-1].part, \
            self.AGV_2[instance_no-1].tray, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1])}
        # print("AGV_2_{} is going from D to {} with part {} with tray {}, elec {}, time{}\n".format(instance_no-1, node, self.AGV_2[instance_no-1].part, \
        #     self.AGV_2[instance_no-1].tray, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1]))
        

    ## 区域二AGV把负载的物料和托盘放到加工区PA
    def AGV_put_partAndtray_on_PA(self, instance_no):
        self.PA_condition.oc_list.append(self.AGV_2[instance_no-1].part)
        self.PA_condition.tray_list.append(self.AGV_2[instance_no-1].tray)
        self.PA_condition.rt_list.append(self.total_time_recorder[1, instance_no-1] + self.t_P)
        print("AGV_2_{} is putting part {} and tray {} on PA, elec {}, time{}\n".format(instance_no-1, self.AGV_2[instance_no-1].part, \
            self.AGV_2[instance_no-1].tray, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1]))
        self.AGV_2[instance_no-1].part = None
        self.AGV_2[instance_no-1].tray = None
        self.PA_condition.cancel_reserve_after_reach()
        
    ## 区域二AGV把负载的物料和托盘放到加工区PB
    def AGV_put_partAndtray_on_PB(self, instance_no):
        self.PB_condition.oc_list.append(self.AGV_2[instance_no-1].part)
        self.PB_condition.tray_list.append(self.AGV_2[instance_no-1].tray)
        self.PB_condition.rt_list.append(self.total_time_recorder[1, instance_no-1] + self.t_P)
        print("AGV_2_{} is putting part {} with tray {} on PB, elec {}, time{}\n".format(instance_no-1, self.AGV_2[instance_no-1].part, \
            self.AGV_2[instance_no-1].tray, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1]))
        self.AGV_2[instance_no-1].part = None
        self.AGV_2[instance_no-1].tray = None
        self.PB_condition.cancel_reserve_after_reach()
        

    ## 区域二AGV把负载的物料和托盘放到缓存区C
    def AGV_put_partAndtray_on_C(self, instance_no):
        self.C_condition.oc_list.append(self.AGV_2[instance_no-1].part)
        self.C_condition.tray_list.append(self.AGV_2[instance_no-1].tray)
        self.AGV_2[instance_no-1].part = None
        self.AGV_2[instance_no-1].tray = None
        self.C_condition.cancel_reserve_after_reach()
        print("AGV_2_{} is putting part {} and tray {} on C, elec {}, time{}\n".format(instance_no-1, self.AGV_2[instance_no-1].part, \
            self.AGV_2[instance_no-1].tray, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1]))
    
    ## 区域二AGV从不同结点返回充电区域E2
    def AGV_go_E2(self, instance_no, node):
        cur_node = 'E2'
        if node == 'SA':
            self.central_control(self.t_SA_E2, (2, instance_no))
            self.AGV_2[instance_no-1].elec -= self.t_SA_E2*self.elec_consume_withpart
        elif node == 'PA':
            self.central_control(self.t_PA_E2, (2, instance_no))
            self.AGV_2[instance_no-1].elec -= self.t_PA_E2*self.elec_consume_withpart
        elif node == 'PB':
            self.central_control(self.t_PB_E2, (2, instance_no))
            self.AGV_2[instance_no-1].elec -= self.t_PB_E2*self.elec_consume_withpart
        elif node == 'C':
            self.central_control(self.t_C_E2, (2, instance_no))
            self.AGV_2[instance_no-1].elec -= self.t_C_E2*self.elec_consume_withpart
        else:
            print("wrong location given")
        self.total_time_recorder[1,instance_no-1], self.time_queue = self.time_correction(self.time_queue, self.total_time_recorder[1,instance_no-1])
        time = self.total_time_recorder[1,instance_no-1]
        self.E2.reserve_position()
        self.agv_action_buffer[time] = {'location':(2,instance_no), 'node': cur_node, 'action':"AGV_2_{} is going from {} to {} with part {} with tray {}, elec {}, time{}".format(instance_no-1, node, cur_node \
         , self.AGV_2[instance_no-1].part, self.AGV_2[instance_no-1].tray, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1])}
        # print("AGV_2_{} is going from {} to {} with part {} with tray {}, elec {}, time{}".format(instance_no-1, node, cur_node \
        #  , self.AGV_2[instance_no-1].part, self.AGV_2[instance_no-1].tray, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1]))

    ## 区域二AGV从加工区PA拿一个托盘返回上料口SA
    def AGV_carry_tray_from_PA(self, instance_no, id):
        tray = self.PA_condition.tray_list.pop(id)
        t = self.PA_condition.rt_list.pop(id)
        part = self.PA_condition.oc_list.pop(id)
        self.finish_parts_PA.remove(part)
        self.AGV_2[instance_no-1].tray = tray
        self.PA_condition.cancel_reserve_after_take()
        cur_node = 'SA'
        self.central_control(self.t_SA_PA + max(0, t - self.total_time_recorder[1,instance_no-1]), (2, instance_no))
        self.AGV_2[instance_no-1].elec -= self.t_SA_PA*self.elec_consume_empty
        self.total_time_recorder[1,instance_no-1], self.time_queue = self.time_correction(self.time_queue, self.total_time_recorder[1,instance_no-1])
        time = self.total_time_recorder[1,instance_no-1]
        self.agv_action_buffer[time] = {'location':(2,instance_no), 'node': cur_node, 'action': "AGV_2_{} is putting part {} tray {} from PA to {}, elec {}, time{}\n".format(instance_no-1, self.AGV_2[instance_no-1].part, self.AGV_2[instance_no-1].tray,\
            cur_node, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1])}
        # print("AGV_2_{} is putting part {} tray {} from PA to {}, elec {}, time{}\n".format(instance_no-1, self.AGV_2[instance_no-1].part, self.AGV_2[instance_no-1].tray,\
        #     cur_node, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1]))
    
    ## 区域二AGV从加工区PB拿一个托盘返回提升机D/缓存区C
    def AGV_carry_tray_from_PB(self, instance_no, id, node):
        tray = self.PB_condition.tray_list.pop(id)
        t = self.PB_condition.rt_list.pop(id)
        part = self.PB_condition.oc_list.pop(id)
        self.finish_parts_PB.remove(part)
        self.AGV_2[instance_no-1].tray = tray
        self.PB_condition.cancel_reserve_after_take()
        if node == 'D':
            self.D_out_condition.reserve_position()
            self.central_control(self.t_D_PB + max(0, t - self.total_time_recorder[1,instance_no-1]), (2, instance_no))
            self.AGV_2[instance_no-1].elec -= self.t_D_PB*self.elec_consume_empty
        elif node == 'C':
            self.C_condition.reserve_position()
            self.central_control(self.t_C_PB + max(0, t - self.total_time_recorder[1,instance_no-1]), (2, instance_no))
            self.AGV_2[instance_no-1].elec -= self.t_C_PB*self.elec_consume_empty
        else:
            print("wrong location given")
        self.total_time_recorder[1,instance_no-1], self.time_queue = self.time_correction(self.time_queue, self.total_time_recorder[1,instance_no-1])
        time = self.total_time_recorder[1,instance_no-1]
        self.agv_action_buffer[time] = {'location':(2,instance_no), 'node': node, 'action': "AGV_2_{} is going from PB to {} with part {} with tray {}, elec {}, time{}\n".format(instance_no-1, node, self.AGV_2[instance_no-1].part, \
            self.AGV_2[instance_no-1].tray, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1])}
        # print("AGV_2_{} is going from PB to {} with part {} with tray {}, elec {}, time{}\n".format(instance_no-1, node, self.AGV_2[instance_no-1].part, \
        #     self.AGV_2[instance_no-1].tray, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1]))
    
    ## 区域二AGV从缓存区C拿一个托盘返回提升机D
    def AGV_carry_tray_from_C_to_D(self, instance_no, id):
        tray = self.C_condition.tray_list.pop(id)
        self.C_condition.oc_list.pop(id)
        self.AGV_2[instance_no-1].tray = tray
        self.C_condition.cancel_reserve_after_take()
        self.central_control(self.t_C_D, (2, instance_no))
        self.AGV_2[instance_no-1].elec -= self.t_C_D*self.elec_consume_empty
        self.D_out_condition.reserve_position()
        self.total_time_recorder[1,instance_no-1], self.time_queue = self.time_correction(self.time_queue, self.total_time_recorder[1,instance_no-1])
        time = self.total_time_recorder[1,instance_no-1]
        self.agv_action_buffer[time] = {'location':(2,instance_no), 'node': 'D', 'action': "AGV_2_{} is going from C to D with part {} with tray {}, elec {}, time{}\n".format(instance_no-1, self.AGV_2[instance_no-1].part, \
            self.AGV_2[instance_no-1].tray, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1])}
        # print("AGV_2_{} is going from C to D with part {} with tray {}, elec {}, time{}\n".format(instance_no-1, self.AGV_2[instance_no-1].part, \
        #     self.AGV_2[instance_no-1].tray, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1]))

    ## 区域二AGV把托盘放到上料口SA/缓存区C/提升机D
    def AGV_2_put_tray(self, instance_no, node):
        if node == 'SA':
            self.SA_condition.SA_tray.append(self.AGV_2[instance_no-1].tray)
            self.SA_condition.tray_count += 1
        elif node == 'C':
            self.C_condition.tray_list.append(self.AGV_2[instance_no-1].tray)
            self.C_condition.oc_list.append(None)
            self.C_condition.cancel_reserve_after_reach()
        elif node == 'D':
            idx = self.D_out_condition.return_put_partortray_pos()
            waiting = max(0, self.D_out_condition.return_put_waiting_time()-self.total_time_recorder[1,instance_no-1])
            self.central_control(waiting, (2, instance_no))
            self.D_out_condition.put_partortray(self.AGV_2[instance_no-1].part, self.AGV_2[instance_no-1].tray, self.total_time_recorder[1,instance_no-1], idx)
        else:
            print("wrong position for the tray")
        print("AGV_2_{} is putting part {} tray {} on {}, elec {}, time{}\n".format(instance_no-1, self.AGV_2[instance_no-1].part, self.AGV_2[instance_no-1].tray,\
            node, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1]))
        self.AGV_2[instance_no-1].tray = None

    # 区域二AGV从充电区域E2返回各个其他点位
    def AGV_go_from_E2(self, instance_no, node):
        self.central_control((100-self.AGV_2[instance_no-1].elec)/self.elec_charge_speed, (2, instance_no))
        self.AGV_2[instance_no-1].elec = 100
        if node == 'SA':
            self.central_control(self.t_SA_E2, (2, instance_no))
            self.AGV_2[instance_no-1].elec -= self.t_SA_E2*self.elec_consume_empty
        elif node == 'PA':
            self.central_control(self.t_PA_E2, (2, instance_no))
            self.AGV_2[instance_no-1].elec -= self.t_PA_E2*self.elec_consume_empty
        elif node == 'C':
            self.central_control(self.t_C_E2, (2, instance_no))
            self.AGV_2[instance_no-1].elec -= self.t_C_E2*self.elec_consume_empty
        elif node == 'PB':
            self.central_control(self.t_PB_E2, (2, instance_no))
            self.AGV_2[instance_no-1].elec -= self.t_PB_E2*self.elec_consume_empty
        elif node == 'D':
            self.central_control(self.t_D_E2, (2, instance_no))
            self.AGV_2[instance_no-1].elec -= self.t_D_E2*self.elec_consume_empty
        else:
            print("wrong goal position given")
        self.total_time_recorder[1,instance_no-1], self.time_queue = self.time_correction(self.time_queue, self.total_time_recorder[1,instance_no-1])
        time = self.total_time_recorder[1,instance_no-1]
        self.agv_action_buffer[time] = {'location':(2,instance_no), 'node': node, 'action': "AGV_2_{} is carrying part {} tray {} from E2 to {}, elec {}, time{}\n".format(instance_no-1, self.AGV_2[instance_no-1].part, self.AGV_2[instance_no-1].tray,\
            node, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1])}
        # print("AGV_2_{} is carrying part {} tray {} from E2 to {}, elec {}, time{}\n".format(instance_no-1, self.AGV_2[instance_no-1].part, self.AGV_2[instance_no-1].tray,\
        #     node, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1]))

    ## 区域二AGV从一个点位到另一个点位运行
    def AGV_2_go_from_one_to_another(self, instance_no, node1, node2):
        self.central_control(eval('self.t_'+node1+'_'+node2), (2, instance_no))
        self.AGV_2[instance_no-1].elec -= eval('self.t_'+node1+'_'+node2)*self.elec_consume_empty
        self.total_time_recorder[1,instance_no-1], self.time_queue = self.time_correction(self.time_queue, self.total_time_recorder[1,instance_no-1])
        time = self.total_time_recorder[1,instance_no-1]
        self.agv_action_buffer[time] = {'location':(2,instance_no), 'node': node2, 'action': "AGV_2_{} is going from {} to {} with part {} with tray {}, elec {}, time{}\n".format(instance_no-1, node1, node2, self.AGV_2[instance_no-1].part, \
            self.AGV_2[instance_no-1].tray, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1])}
        # print("AGV_2_{} is going from {} to {} with part {} with tray {}, elec {}, time{}\n".format(instance_no-1, node1, node2, self.AGV_2[instance_no-1].part, \
        #     self.AGV_2[instance_no-1].tray, self.AGV_2[instance_no-1].elec, self.total_time_recorder[1,instance_no-1]))

    ## 给出从SA拿物料去PA或者C的奖励函数
    def return_f_goingFrom_SA_to_PAorC(self, instance_no):
        if not self.SA_condition.check_reserve_full():
            waiting_time = max(0, (self.SA_condition.part_count+self.SA_condition.reserve_count)*self.part_freq-self.total_time_recorder[1, instance_no-1])
            if not self.PA_condition.check_full():
                f1 = -waiting_time*self.t_fac + self.take_part - self.t_SA_PA*self.s_fac + self.put_part1
                f2 = self.minus_inf
            elif not self.C_condition.check_full():
                f1 = self.minus_inf
                f2 = -waiting_time*self.t_fac + self.take_part - self.t_SA_C*self.s_fac + self.put_part2
            else:
                f1 = self.minus_inf
                f2 = self.minus_inf
        else:
            print("reserve full")
            f1 = self.minus_inf
            f2 = self.minus_inf
        return f1, f2

    ##############################################################################
    # 区域一AGV运动函数
    ##############################################################################
    
    ## 区域一AGV从上料口SB拿起一个物料和托盘，前往提升机D
    ## 返回：下一个结点D
    def AGV_wait_and_carry_partAndtray_from_SB_to_D(self, instance_no):
        if self.SB_condition.part_count == 0:
            self.AGV_1[instance_no-1].part = self.SB_condition.parts_SB.pop(0)
            self.AGV_1[instance_no-1].tray = self.SB_condition.SB_tray.pop(0)
            self.SB_condition.part_count += 1
        elif self.total_time_recorder[0,instance_no-1] >= (self.SB_condition.part_count+self.SB_condition.reserve_count)*self.part_freq:
            self.AGV_1[instance_no-1].part = self.SB_condition.parts_SB.pop(0)
            self.AGV_1[instance_no-1].tray = self.SB_condition.SB_tray.pop(0)
            self.SB_condition.part_count += 1
        else:
            # print(self.SB_condition.part_count)
            # print("No part in SB currently, please waiting.")
            self.central_control(self.SB_condition.part_count*self.part_freq-self.total_time_recorder[0,instance_no-1], (1, instance_no))
            self.AGV_1[instance_no-1].part = self.SB_condition.parts_SB.pop(0)
            self.AGV_1[instance_no-1].tray = self.SB_condition.SB_tray.pop(0)
            self.SB_condition.part_count += 1
        cur_node = 'D'
        self.central_control(self.t_SB_D, (1, instance_no))
        self.total_time_recorder[0,instance_no-1], self.time_queue = self.time_correction(self.time_queue, self.total_time_recorder[0,instance_no-1])
        time = self.total_time_recorder[0,instance_no-1]
        self.D_in_condition.reserve_position()
        self.AGV_1[instance_no-1].elec -= self.t_SB_D*self.elec_consume_withpart
        self.agv_action_buffer[time] = {'location':(1,instance_no), 'node': cur_node, 'action':"AGV_1_{} is carrying part {} tray {} to D, elec {}, time{}\n".format(instance_no-1, self.AGV_1[instance_no-1].part, self.AGV_1[instance_no-1].tray,\
            self.AGV_1[instance_no-1].elec, self.total_time_recorder[0,instance_no-1])}
        # print("AGV_1_{} is carrying part {} tray {} to D, elec {}, time{}\n".format(instance_no-1, self.AGV_1[instance_no-1].part, self.AGV_1[instance_no-1].tray,\
        #     self.AGV_1[instance_no-1].elec, self.total_time_recorder[0,instance_no-1]))
        return cur_node

    # 区域一AGV把负载的物料和托盘放到提升机D
    def AGV_put_partAndtray_on_D(self, instance_no):
        part = self.AGV_1[instance_no-1].part
        tray = self.AGV_1[instance_no-1].tray
        idx = self.D_in_condition.return_put_partortray_pos()
        self.D_in_condition.put_partortray(part, tray, self.total_time_recorder[0, instance_no-1], idx)
        # print(self.D_in_condition.oc_list)
        # print(self.D_in_condition.tray_list)
        # print(self.D_in_condition.rt_list_in)
        # print(self.D_in_condition.rt_list_out)
        print("AGV_1_{} is putting part {} tray {} on D, elec {}, time{}\n".format(instance_no-1, self.AGV_1[instance_no-1].part, self.AGV_1[instance_no-1].tray,\
            self.AGV_1[instance_no-1].elec, self.total_time_recorder[0,instance_no-1]))
        self.AGV_1[instance_no-1].part = None
        self.AGV_1[instance_no-1].tray = None
        self.D_in_condition.cancel_reserve_after_reach()

    # 区域一AGV从提升机D拿起一个托盘，前往SB
    def AGV_carry_tray_from_D_to_SB(self, instance_no):
        idx = self.D_out_condition.return_take_partortray_pos()
        waiting = max(self.D_out_condition.return_take_waiting_time()-self.total_time_recorder[0, instance_no-1], 0)
        part, tray = self.D_out_condition.take_partortray(idx, self.total_time_recorder[0, instance_no-1])
        self.central_control(waiting + self.t_SB_D, (1, instance_no))
        self.total_time_recorder[0,instance_no-1], self.time_queue = self.time_correction(self.time_queue, self.total_time_recorder[0,instance_no-1])
        time = self.total_time_recorder[0,instance_no-1]
        self.AGV_1[instance_no-1].part = part
        self.AGV_1[instance_no-1].tray = tray
        self.AGV_1[instance_no-1].elec -= self.t_SB_D*self.elec_consume_withpart
        self.agv_action_buffer[time] = {'location':(1,instance_no), 'node': 'SB', 'action':"AGV_1_{} is taking part {} tray {} from D to SB, elec {}, time{}\n".format(instance_no-1, self.AGV_1[instance_no-1].part, self.AGV_1[instance_no-1].tray,\
            self.AGV_1[instance_no-1].elec, self.total_time_recorder[0,instance_no-1])}
        # print("AGV_1_{} is taking part {} tray {} from D to SB, elec {}, time{}\n".format(instance_no-1, self.AGV_1[instance_no-1].part, self.AGV_1[instance_no-1].tray,\
        #     self.AGV_1[instance_no-1].elec, self.total_time_recorder[0,instance_no-1]))

    # 区域一AGV把托盘放到上料口SB
    def AGV_put_tray_on_SB(self, instance_no):
        self.SB_condition.SB_tray.append(self.AGV_1[instance_no-1].tray)
        self.SB_condition.tray_count += 1
        print("AGV_1_{} is putting part {} tray {} on SB, elec {}, time{}\n".format(instance_no-1, self.AGV_1[instance_no-1].part, self.AGV_1[instance_no-1].tray,\
            self.AGV_1[instance_no-1].elec, self.total_time_recorder[0,instance_no-1]))
        self.AGV_1[instance_no-1].tray = None

    ## 区域一AGV返回充电区域E1
    def AGV_go_E1(self, instance_no, node):
        cur_node = 'E1'
        if node == 'SB':
            self.central_control(self.t_SB_E1, (1, instance_no))
            self.AGV_1[instance_no-1].elec -= self.t_SB_E1*self.elec_consume_withpart
        elif node == 'D':
            self.central_control(self.t_D_E1, (1, instance_no))
            self.AGV_1[instance_no-1].elec -= self.t_D_E1*self.elec_consume_withpart
        else:
            print("wrong location given")
        self.total_time_recorder[0,instance_no-1], self.time_queue = self.time_correction(self.time_queue, self.total_time_recorder[0,instance_no-1])
        time = self.total_time_recorder[0,instance_no-1]
        self.E1.reserve_position()
        self.agv_action_buffer[time] = {'location':(1,instance_no), 'node': cur_node, 'action':"AGV_1_{} is going from {} to {} with part {} with tray {}, elec {}, time{}".format(instance_no-1, node, cur_node \
         , self.AGV_1[instance_no-1].part, self.AGV_1[instance_no-1].tray, self.AGV_1[instance_no-1].elec, self.total_time_recorder[0,instance_no-1])}
        # print("AGV_1_{} is going from {} to {} with part {} with tray {}, elec {}, time{}".format(instance_no-1, node, cur_node \
        #  , self.AGV_1[instance_no-1].part, self.AGV_1[instance_no-1].tray, self.AGV_1[instance_no-1].elec, self.total_time_recorder[0,instance_no-1]))
        return cur_node
    
    # 区域一AGV从充电区域返回各个其他点位
    def AGV_go_from_E1(self, instance_no, node):
        self.central_control((100-self.AGV_1[instance_no-1].elec)/self.elec_charge_speed, (1, instance_no))
        self.AGV_1[instance_no-1].elec = 100
        if node == 'SB':
            self.central_control(self.t_SB_E1, (1, instance_no))
            self.AGV_1[instance_no-1].elec -= self.t_SB_E1*self.elec_consume_empty
        elif node == 'D':
            self.central_control(self.t_D_E1, (1, instance_no))
            self.AGV_1[instance_no-1].elec -= self.t_D_E1*self.elec_consume_empty
        else:
            print("wrong goal position given")
        self.total_time_recorder[0,instance_no-1], self.time_queue = self.time_correction(self.time_queue, self.total_time_recorder[0,instance_no-1])
        time = self.total_time_recorder[0,instance_no-1]
        self.agv_action_buffer[time] = {'location':(1,instance_no), 'node': node, 'action':"AGV_1_{} is carrying part {} tray {} from E1 to {}, elec {}, time{}\n".format(instance_no-1, self.AGV_1[instance_no-1].part, self.AGV_1[instance_no-1].tray,\
            node, self.AGV_1[instance_no-1].elec, self.total_time_recorder[0,instance_no-1])}
        # print("AGV_1_{} is carrying part {} tray {} from E1 to {}, elec {}, time{}\n".format(instance_no-1, self.AGV_1[instance_no-1].part, self.AGV_1[instance_no-1].tray,\
        #     node, self.AGV_1[instance_no-1].elec, self.total_time_recorder[0,instance_no-1]))
          
    # 区域一AGV从一个点位到另一个点位运行
    def AGV_1_go_from_one_to_another(self, instance_no, node1, node2):
        self.central_control(self.t_SB_D, (2, instance_no))
        self.total_time_recorder[0,instance_no-1], self.time_queue = self.time_correction(self.time_queue, self.total_time_recorder[0,instance_no-1])
        time = self.total_time_recorder[0,instance_no-1]
        self.AGV_2[instance_no-1].elec -= self.t_SB_D*self.elec_consume_empty
        self.agv_action_buffer[time] = {'location':(1,instance_no), 'node': node2, 'action': "AGV_1_{} is going from {} to {} with part {} with tray {}, elec {}, time{}\n".format(instance_no-1, node1, node2, self.AGV_2[instance_no-1].part, \
            self.AGV_1[instance_no-1].tray, self.AGV_1[instance_no-1].elec, self.total_time_recorder[0,instance_no-1])}
        # print("AGV_1_{} is going from {} to {} with part {} with tray {}, elec {}, time{}\n".format(instance_no-1, node1, node2, self.AGV_2[instance_no-1].part, \
        #     self.AGV_1[instance_no-1].tray, self.AGV_1[instance_no-1].elec, self.total_time_recorder[0,instance_no-1]))


    # 区域二AGV运动逻辑
    def AGV_region_2(self, instance_no, cur_node_2):
        # 区域二AGV初始化在SA
        f_list = []
        index = 0 
        first_allocate = True
        is_waiting = False
        last_waiting = self.waiting_list_2[instance_no-1]

        f_list = []

        if cur_node_2 == 'SA':   
            # AGV初始化时，应该有一个单独的决策过程
            if first_allocate:
                first_allocate = False
            
            # 若AGV电量不足，则去充电
            if self.AGV_2[instance_no-1].elec <= 20:
                # 若AGV带有托盘，则先回收托盘
                if self.AGV_2[instance_no-1].tray is not None:
                    self.AGV_2_put_tray(instance_no, cur_node_2)
                # 若E2有空位置，则前往，否则原地等待
                print(self.E2.reserve_num)
                if not self.E2.check_full():
                    self.AGV_go_E2(instance_no, cur_node_2)
                    cur_node_2 = 'E2'
                    return is_waiting, cur_node_2
                else:
                    print("E2 is full, AGV_2_{} is waiting in {}".format(instance_no-1, cur_node_2))
                    is_waiting = True
                    return is_waiting, cur_node_2
            # AGV开始做下一步动作的决策，分两类
            # 第一类：AGV空车前来（不携带托盘），那么AGV肯定是前来拿物料的，在决策时，SA物料不足的情况不会发生
            if self.AGV_2[instance_no-1].tray is None:
#########################################################################################################################
                # self.SA_condition.cancel_reserve()
#########################################################################################################################
                # 如果有物料和托盘，根据55秒来一个物料计算等待时间并发放物料和托盘
                if len(self.SA_condition.parts_SA) > 0 and len(self.SA_condition.SA_tray) > 0:      
                    if not self.PA_condition.check_full():
                        cur_node_2 = 'PA'
                        self.AGV_wait_and_carry_partAndtray_from_SA(instance_no, cur_node_2)
                        return is_waiting, cur_node_2
                    elif not self.C_condition.check_full():
                        cur_node_2 = 'C'
                        self.AGV_wait_and_carry_partAndtray_from_SA(instance_no, cur_node_2)
                        return is_waiting, cur_node_2
                    else:
                        # print("PA and C are full, AGV_2_{} is waiting in {}".format(instance_no, cur_node_2))
                        # continue
                        pass
                else:
                    # print("No tray in SA now, AGV_2_{} is waiting in {}".format(instance_no, cur_node_2))
                    # continue
                    pass
            # 第二类：如果AGV有托盘，那先放托盘，再做决策。
            # 同时，上面一类中pass的情况也用第二类做决策
            # 先计算每一个决策的奖励函数
            if self.AGV_2[instance_no-1].tray is not None:
                self.AGV_2_put_tray(instance_no, cur_node_2)
            f1, f2 = self.return_f_goingFrom_SA_to_PAorC(instance_no)
            if not self.C_condition.check_reserve_trayorpart_full() and not self.C_condition.check_empty():
                f3 = -self.t_SA_C*self.s_fac + self.take_part
            else:
                f3 = self.minus_inf
            # 去D拿物料
            if self.D_in_condition.check_out_pos_available() and not self.D_in_condition.check_reserve_trayorpart_full():
                waiting_time = max(self.D_in_condition.return_take_waiting_time()-self.total_time_recorder[1,instance_no-1]-self.t_SA_D,0)
                f4 = -self.t_SA_D*self.s_fac - waiting_time*self.t_fac + self.take_part
            else:
                f4 = self.minus_inf
            if not self.PA_condition.check_reserve_trayorpart_full() and not self.PA_condition.check_empty():
                waiting_time = max(self.PA_condition.waiting_time_calculate()-self.total_time_recorder[1,instance_no-1]-self.t_SA_PA,0)
                f5 = -self.t_SA_PA*self.s_fac - waiting_time*self.t_fac + self.take_part
            else:
                f5 = self.minus_inf
            if not self.PB_condition.check_reserve_trayorpart_full() and not self.PB_condition.check_empty():
                waiting_time = max(self.PB_condition.waiting_time_calculate()-self.total_time_recorder[1,instance_no-1]-self.t_SA_PB,0)
                f6 = -self.t_SA_PB*self.s_fac - waiting_time*self.t_fac + self.take_part
            else:
                f6 = self.minus_inf
            f_list.extend((f1, f2, f3, f4, f5, f6))
            # print(f_list)
            # print(self.PB_condition.check_reserve_trayorpart_full())
            # print(self.PB_condition.check_empty())
            # print(self.PB_condition.tray_list)
            # print(self.PB_condition.reserve_tray_num)
            # print(self.D_in_condition.rt_list_in)
            # print(self.D_in_condition.rt_list_out)
            if max(f_list) == self.minus_inf:
                # a = np.random.randint(0,10)
                # b = np.random.randint(0,10)
                # if a > b:
                #     cur_node_2 = 'C'
                #     self.AGV_2_go_from_one_to_another(instance_no, 'SA', cur_node_2)
                #     continue
                # else:
                #     cur_node_2 = 'D'
                #     self.AGV_2_go_from_one_to_another(instance_no, 'SA', cur_node_2)
                #     continue
                print("AGV_2_{} is waiting in SA".format(instance_no-1))
                is_waiting = True
                return is_waiting, cur_node_2

            index = f_list.index(max(f_list))
            if index == 0:
                cur_node_2 = 'PA'
                self.AGV_wait_and_carry_partAndtray_from_SA(instance_no, cur_node_2)
                return is_waiting, cur_node_2
            elif index == 1:
                cur_node_2 = 'C'
                self.AGV_wait_and_carry_partAndtray_from_SA(instance_no, cur_node_2)
                return is_waiting, cur_node_2
            elif index == 2:
                cur_node_2 = 'C'
                self.AGV_2_go_from_one_to_another(instance_no, 'SA', cur_node_2)
                self.C_condition.reserve_take_trayorpart()
                return is_waiting, cur_node_2
            elif index == 3:
                # print("In SA, the D oc_list {}".format(self.D_in_condition.oc_list))
                # print("In SA, the D tray_list {}".format(self.D_in_condition.tray_list))
                # print("In SA, the D reserve_num {}".format(self.D_in_condition.reserve_tray_num))
                # print("In SA, the D reserve full{}".format(self.D_in_condition.check_reserve_trayorpart_full()))
                cur_node_2 = 'D'
                self.AGV_2_go_from_one_to_another(instance_no, 'SA', cur_node_2)
                self.D_in_condition.reserve_take_trayorpart()
                return is_waiting, cur_node_2
            elif index == 4:
                cur_node_2 = 'PA'
                self.AGV_2_go_from_one_to_another(instance_no, 'SA', cur_node_2)
                self.PA_condition.reserve_take_trayorpart()
                return is_waiting, cur_node_2
            else:
                cur_node_2 = 'PB'
                self.AGV_2_go_from_one_to_another(instance_no, 'SA', cur_node_2)
                self.PB_condition.reserve_take_trayorpart()
                return is_waiting, cur_node_2

        elif cur_node_2 == 'PA':
            if self.AGV_2[instance_no-1].elec <= 20:
                # 若AGV无物料，则需要先取消之前的预约
                if self.AGV_2[instance_no-1].part is None:
                    self.PA_condition.cancel_reserve_after_take()
                # 若AGV带有物料，则先放置物料
                if self.AGV_2[instance_no-1].part is not None:
                    self.AGV_put_partAndtray_on_PA(instance_no)
                # 若E2有空位置，则前往，否则原地等待
                if not self.E2.check_full():
                    self.AGV_go_E2(instance_no, cur_node_2)
                    cur_node_2 = 'E2'
                    return is_waiting, cur_node_2
                else:
                    print("E2 is full, AGV_2_{} is waiting in {}".format(instance_no-1, cur_node_2))
                    is_waiting = True
                    return is_waiting, cur_node_2
            if self.AGV_2[instance_no-1].part is None and last_waiting == None: 
                tray_index = self.PA_condition.rt_list.index(min(self.PA_condition.rt_list))  
                cur_node_2 = 'SA'
                self.AGV_carry_tray_from_PA(instance_no, tray_index)  
                # print("agv come to pa withour part and take tray, after putting part on SA")
                # print(self.PA_condition.tray_list)
                # print(self.PA_condition.reserve_tray_num)
                # print(self.PA_condition.rt_list) 
                return is_waiting, cur_node_2
            if last_waiting == None:           
                self.AGV_put_partAndtray_on_PA(instance_no)
            # 计算各个策略的奖励函数
            # PA拿托盘，前往SA放托盘
            if not self.PA_condition.check_reserve_trayorpart_full() and not self.PA_condition.check_empty():
                waiting_time = max(self.PA_condition.waiting_time_calculate()-self.total_time_recorder[1,instance_no-1],0)
                f1 = -waiting_time*self.t_fac + self.take_part - self.t_SA_PA*self.s_fac + self.put_part1
            else:
                f1 = self.minus_inf
            # 前往SA拿新的物料
            if not self.SA_condition.check_reserve_full():
                waiting_time = max(0, (self.SA_condition.part_count+self.SA_condition.reserve_count)*self.part_freq-self.total_time_recorder[1,instance_no-1])
                f2 = -self.t_SA_PA*self.s_fac - max(0, waiting_time-self.t_SA_PA)*self.t_fac + self.take_part
            else:
                f2 = self.minus_inf
            # 前往C拿物料/托盘
            if not self.C_condition.check_reserve_trayorpart_full() and not self.C_condition.check_empty():
                f3 = -self.t_SA_C*self.s_fac + self.take_part
            else:
                f3 = self.minus_inf 
            # 前往PB拿托盘
            if not self.PB_condition.check_reserve_trayorpart_full() and not self.PB_condition.check_empty():
                waiting_time = max(self.PB_condition.waiting_time_calculate()-self.total_time_recorder[1,instance_no-1]-self.t_PA_PB,0)
                f4 = -self.t_PA_PB*self.s_fac - waiting_time*self.t_fac + self.take_part
            else:
                f4 = self.minus_inf
            # 前往D拿物料
            if self.D_in_condition.check_out_pos_available() and not self.D_in_condition.check_reserve_trayorpart_full():
                waiting_time = max(self.D_in_condition.return_take_waiting_time()-self.total_time_recorder[1,instance_no-1]-self.t_SA_D,0)
                f5 = -self.t_SA_D*self.s_fac - waiting_time*self.t_fac + self.take_part
            else:
                f5 = self.minus_inf 
            f_list.extend((f1, f2, f3, f4, f5))
            # print(f_list)
            if max(f_list) != self.minus_inf:
                is_waiting = False
                index = f_list.index(max(f_list))
                if index == 0:
                    cur_node_2 = 'SA'
                    tray_index = self.PA_condition.rt_list.index(min(self.PA_condition.rt_list))  
                    self.PA_condition.reserve_take_trayorpart()
                    self.AGV_carry_tray_from_PA(instance_no, tray_index) 
                    # print("agv decide to take tray to SA, after putting part on SA")
                    # print(self.PA_condition.tray_list)
                    # print(self.PA_condition.reserve_tray_num)
                    # print(self.PA_condition.rt_list)   
                    return is_waiting, cur_node_2
                elif index == 1:
                    cur_node_2 = 'SA'
                    self.AGV_2_go_from_one_to_another(instance_no, 'PA', cur_node_2)
                    return is_waiting, cur_node_2
                elif index == 2:
                    cur_node_2 = 'C'
                    self.AGV_2_go_from_one_to_another(instance_no, 'PA', cur_node_2)
                    self.C_condition.reserve_take_trayorpart()
                    return is_waiting, cur_node_2
                elif index == 3:
                    cur_node_2 = 'PB'
                    self.AGV_2_go_from_one_to_another(instance_no, 'PA', cur_node_2)
                    self.PB_condition.reserve_take_trayorpart()
                    return is_waiting, cur_node_2
                elif index == 4:
                    cur_node_2 = 'D'
                    self.AGV_2_go_from_one_to_another(instance_no, 'PA', cur_node_2)
                    self.D_in_condition.reserve_take_trayorpart()
                    return is_waiting, cur_node_2
            else:
                print("AGV_2_{} is waiting in PA".format(instance_no-1))
                is_waiting = True
                return is_waiting, cur_node_2

        elif cur_node_2 == 'PB':
            if self.AGV_2[instance_no-1].elec <= 20:
                # 若AGV带有物料，则先放置物料
                if self.AGV_2[instance_no-1].part is None:
                    self.PB_condition.cancel_reserve_after_take()
                if self.AGV_2[instance_no-1].part is not None:
                    self.AGV_put_partAndtray_on_PB(instance_no)
                # 若E2有空位置，则前往，否则原地等待
                if not self.E2.check_full():
                    self.AGV_go_E2(instance_no, cur_node_2)
                    cur_node_2 = 'E2'
                    return is_waiting, cur_node_2
                else:
                    print("E2 is full, AGV_2_{} is waiting in {}".format(instance_no-1, cur_node_2))
                    is_waiting = True
                    return is_waiting, cur_node_2

            if self.AGV_2[instance_no-1].part is None and last_waiting == None: 
                if not self.PB_condition.check_empty():
                    # 回收托盘
                    tray_index = self.PB_condition.rt_list.index(min(self.PB_condition.rt_list))  
                    # self.PA_condition.reserve_take_trayorpart()
                    # print(self.D_out_condition.oc_list)
                    # print(self.D_out_condition.tray_list)
                    # print(self.D_out_condition.rt_list_in)
                    # print(self.D_out_condition.rt_list_out)
                    # print(self.D_out_condition.check_in_pos_available())
                    # print(self.D_out_condition.check_out_pos_available())
                    if self.D_out_condition.check_in_pos_available() and not self.D_out_condition.check_full():
                        cur_node_2 = 'D'
                        # self.PB_condition.reserve_take_trayorpart()
                        self.AGV_carry_tray_from_PB(instance_no, tray_index, 'D')     
                        return is_waiting, cur_node_2
                    elif not self.C_condition.check_reserve_trayorpart_full():
                        cur_node_2 = 'C'
                        # self.PB_condition.reserve_take_trayorpart()
                        self.AGV_carry_tray_from_PB(instance_no, tray_index, 'C')  
                        return is_waiting, cur_node_2  
                    else:
                        print("D and C are not available now, AGV_2_{} is waiting".format(instance_no))  
                        self.PB_condition.cancel_reserve_after_take()
                        pass
                else:
                    self.PB_condition.cancel_reserve_after_take()
                    pass  
            if self.AGV_2[instance_no-1].part is not None:  
                self.AGV_put_partAndtray_on_PB(instance_no)
            # 计算各个策略的奖励函数
            # PB拿托盘前往D或C
            if not self.PB_condition.check_reserve_trayorpart_full() and not self.PB_condition.check_empty() \
                and self.D_out_condition.check_in_pos_available() and not self.D_out_condition.check_full():
                waiting_time1 = max(self.PB_condition.waiting_time_calculate()-self.total_time_recorder[1,instance_no-1],0)
                waiting_time2 = max(self.D_out_condition.return_put_waiting_time()-self.total_time_recorder[1,instance_no-1]-waiting_time1-self.t_D_PB,0)
                f1 = self.minus_inf
                f2 = -waiting_time1*self.t_fac - self.t_D_PB*self.s_fac - waiting_time2*self.t_fac + self.put_part1   
            elif not self.PB_condition.check_reserve_trayorpart_full() and not self.PB_condition.check_empty() \
                and not self.C_condition.check_reserve_trayorpart_full():
                waiting_time1 = max(self.PB_condition.waiting_time_calculate()-self.total_time_recorder[1,instance_no-1],0)
                waiting_time2 = max(self.D_out_condition.return_put_waiting_time()-self.total_time_recorder[1,instance_no-1]-waiting_time1-self.t_C_D,0)
                f2 = self.minus_inf
                f1 = -waiting_time1*self.t_fac - self.t_C_D*self.s_fac - waiting_time2*self.t_fac + self.put_part1
            else:
                f1 = self.minus_inf
                f2 = self.minus_inf
            # 去SA拿物料
            if not self.SA_condition.check_reserve_full():
                waiting_time = max(0, (self.SA_condition.part_count+self.SA_condition.reserve_count)*self.part_freq-self.total_time_recorder[1,instance_no-1]-self.t_SA_PB)
                f3 = -self.t_SA_PB*self.s_fac - waiting_time*self.t_fac + self.take_part
            else:
                f3 = self.minus_inf 
            # 去C拿物料/托盘
            if not self.C_condition.check_reserve_trayorpart_full() and not self.C_condition.check_empty():
                f4 = -self.t_C_PB*self.s_fac + self.take_part
            else:
                f4 = self.minus_inf 
            # 去PA拿托盘
            if not self.PA_condition.check_reserve_trayorpart_full() and not self.PA_condition.check_empty():
                waiting_time = max(self.PA_condition.waiting_time_calculate()-self.total_time_recorder[1,instance_no-1]-self.t_PA_PB,0)
                f5 = -self.t_PA_PB*self.s_fac - waiting_time*self.t_fac + self.take_part
            else:
                f5 = self.minus_inf
            # 去D拿物料
            if self.D_in_condition.check_out_pos_available() and not self.D_in_condition.check_reserve_trayorpart_full():
                waiting_time = max(self.D_in_condition.return_take_waiting_time()-self.total_time_recorder[1,instance_no-1]-self.t_D_PB,0)
                f6 = -self.t_D_PB*self.s_fac - waiting_time*self.t_fac + self.take_part
            else:
                f6 = self.minus_inf 
            f_list.extend((f1, f2, f3, f4, f5, f6))
            # print(f_list)
            # print(self.PB_condition.check_reserve_trayorpart_full())
            # print(self.PB_condition.tray_list)
            # print(self.PB_condition.reserve_tray_num)
            # print(self.D_in_condition.tray_list)
            # print(self.D_in_condition.reserve_tray_num)
            index = f_list.index(max(f_list))
            if max(f_list) != self.minus_inf:
                is_waiting = False
                if index == 0:
                    cur_node_2 = 'C'
                    tray_index = self.PB_condition.rt_list.index(min(self.PB_condition.rt_list))  
                    self.PB_condition.reserve_take_trayorpart()
                    self.AGV_carry_tray_from_PB(instance_no, tray_index, 'C')  
                    return is_waiting, cur_node_2
                elif index == 1:
                    cur_node_2 = 'D'
                    tray_index = self.PB_condition.rt_list.index(min(self.PB_condition.rt_list))  
                    self.PB_condition.reserve_take_trayorpart()
                    self.AGV_carry_tray_from_PB(instance_no, tray_index, 'D')  
                    return is_waiting, cur_node_2 
                elif index == 2:
                    cur_node_2 = 'SA'
                    self.AGV_2_go_from_one_to_another(instance_no, cur_node_2, 'PB')
                    return is_waiting, cur_node_2
                elif index == 3:
                    cur_node_2 = 'C'
                    self.AGV_2_go_from_one_to_another(instance_no, 'PB', cur_node_2)
                    self.C_condition.reserve_take_trayorpart()
                    return is_waiting, cur_node_2
                elif index == 4:
                    cur_node_2 = 'PA'
                    self.AGV_2_go_from_one_to_another(instance_no, 'PB', cur_node_2)
                    self.PA_condition.reserve_take_trayorpart()
                    # print("agv decide to go to PA take tray")
                    # print(self.PA_condition.tray_list)
                    # print(self.PA_condition.reserve_tray_num)
                    # print(self.PA_condition.rt_list) 
                    return is_waiting, cur_node_2
                elif index == 5:
                    cur_node_2 = 'D'
                    self.AGV_2_go_from_one_to_another(instance_no, 'PB', cur_node_2)
                    self.D_in_condition.reserve_take_trayorpart()
                    return is_waiting, cur_node_2
            else:
                is_waiting = True
                print("AGV_2_{} is waiting in PB".format(instance_no-1))
                return is_waiting, cur_node_2


        elif cur_node_2 == 'C':
            if self.AGV_2[instance_no-1].elec <= 20:
                # 若AGV带有物料，则先放置物料
                if self.AGV_2[instance_no-1].part is not None or self.AGV_2[instance_no-1].tray is not None:
                    self.AGV_put_partAndtray_on_C(instance_no)
                # 若E2有空位置，则前往，否则原地等待
                if not self.E2.check_full():
                    self.AGV_go_E2(instance_no, cur_node_2)
                    cur_node_2 = 'E2'
                    return is_waiting, cur_node_2
                else:
                    print("E2 is full, AGV_2_{} is waiting in {}".format(instance_no-1, cur_node_2))
                    is_waiting = True
                    return is_waiting, cur_node_2
            # 计算所有情况的代价
            # 从C拿托盘前往D
            idx = [i for i, x in enumerate(self.C_condition.oc_list) if x == None]
            index = [i for i, x in enumerate(idx) if self.C_condition.tray_list[x] != None]
            if len(index) > 0 and self.D_out_condition.check_in_pos_available() and not self.D_out_condition.check_full():
                f1 = self.take_part - self.t_C_D*self.s_fac + self.put_part2
            else:
                f1 = self.minus_inf
            # 从C拿物料，前往PA放置物料
            idx = [i for i, x in enumerate(self.C_condition.oc_list) if x != None and x > self.N_parts_SB]
            if len(idx) > 0 and not self.PA_condition.check_reserve_trayorpart_full():
                f2 = self.take_part - self.t_C_PA*self.s_fac + self.put_part1 
            else:
                f2 = self.minus_inf
            # 从C拿物料，前往PB放置物料
            idx = [i for i, x in enumerate(self.C_condition.oc_list) if x != None and x <= self.N_parts_SB]
            if len(idx) > 0 and not self.PB_condition.check_reserve_trayorpart_full():
                f3 = self.take_part - self.t_C_PB*self.s_fac + self.put_part1 
            else:
                f3 = self.minus_inf
            # 前往SA拿新的物料
            if not self.SA_condition.check_reserve_full():
                waiting_time = max(0, (self.SA_condition.part_count+self.SA_condition.reserve_count)*self.part_freq-self.total_time_recorder[1,instance_no-1])
                f4 = -self.t_SA_C*self.s_fac - max(0, waiting_time-self.t_SA_C)*self.t_fac + self.take_part
            else:
                f4 = self.minus_inf
            # 前往PA拿托盘
            if not self.PA_condition.check_reserve_trayorpart_full() and not self.PA_condition.check_empty():
                waiting_time = max(self.PA_condition.waiting_time_calculate()-self.total_time_recorder[1,instance_no-1]-self.t_C_PA,0)
                f5 = -self.t_C_PA*self.s_fac - waiting_time*self.t_fac + self.take_part
            else:
                f5 = self.minus_inf
            # 前往PB拿托盘
            if not self.PB_condition.check_reserve_trayorpart_full() and not self.PB_condition.check_empty():
                waiting_time = max(self.PB_condition.waiting_time_calculate()-self.total_time_recorder[1,instance_no-1]-self.t_C_PB,0)
                f6 = -self.t_C_PB*self.s_fac - waiting_time*self.t_fac + self.take_part
            else:
                f6 = self.minus_inf
            # 前往D拿物料
            if self.D_in_condition.check_out_pos_available() and not self.D_in_condition.check_reserve_trayorpart_full():
                waiting_time = max(self.D_in_condition.return_take_waiting_time()-self.total_time_recorder[1,instance_no-1]-self.t_SA_D,0)
                f7 = -self.t_C_D*self.s_fac - waiting_time*self.t_fac + self.take_part
            else:
                f7 = self.minus_inf
            
            if self.AGV_2[instance_no-1].part is None and self.AGV_2[instance_no-1].tray is None:
                f_list.extend((f1, f2, f3))
                # print(f_list)
                if max(f_list) != self.minus_inf:
                    index = f_list.index(max(f_list))
                    if index == 0:
                        cur_node_2 = 'D'
                        idx = [i for i, x in enumerate(self.C_condition.oc_list) if x == None]
                        index = [i for i, x in enumerate(idx) if self.C_condition.tray_list[x] != None]
                        self.AGV_carry_tray_from_C_to_D(instance_no, index[0])
                        return is_waiting, cur_node_2
                    elif index == 1:
                        cur_node_2 = 'PA'
                        idx = [i for i, x in enumerate(self.C_condition.oc_list) if x != None and x > self.N_parts_SB]
                        self.AGV_carry_partAndtray_from_C(instance_no, idx[0], 'PA')
                        return is_waiting, cur_node_2
                    elif index == 2:
                        cur_node_2 = 'PB'
                        idx = [i for i, x in enumerate(self.C_condition.oc_list) if x != None and x <= self.N_parts_SB]
                        self.AGV_carry_partAndtray_from_C(instance_no, idx[0], 'PB')
                        return is_waiting, cur_node_2
                else:
                    f_list = []
                    pass    
            if self.AGV_2[instance_no-1].part is not None or self.AGV_2[instance_no-1].tray is not None:
                self.AGV_put_partAndtray_on_C(instance_no)    
            f_list.extend((f1, f2, f3, f4, f5, f6, f7))
            if max(f_list) != self.minus_inf:
                is_waiting = False
                index = f_list.index(max(f_list))
                if index == 0:
                    cur_node_2 = 'D'
                    idx = [i for i, x in enumerate(self.C_condition.oc_list) if x == None]
                    index = [i for i, x in enumerate(idx) if self.C_condition.tray_list[x] != None]
                    self.AGV_carry_tray_from_C_to_D(instance_no, idx[0])
                    return is_waiting, cur_node_2
                elif index == 1:
                    cur_node_2 = 'PA'
                    idx = [i for i, x in enumerate(self.C_condition.oc_list) if x != None and x > self.N_parts_SB]
                    self.AGV_carry_partAndtray_from_C(instance_no, idx[0], 'PA')
                    return is_waiting, cur_node_2
                elif index == 2:
                    cur_node_2 = 'PB'
                    idx = [i for i, x in enumerate(self.C_condition.oc_list) if x != None and x <= self.N_parts_SB]
                    self.AGV_carry_partAndtray_from_C(instance_no, idx[0], 'PB')
                    return is_waiting, cur_node_2
                elif index == 3:
                    cur_node_2 = 'SA'
                    self.AGV_2_go_from_one_to_another(instance_no, cur_node_2, 'C')
                    return is_waiting, cur_node_2
                elif index == 4:
                    cur_node_2 = 'PA'
                    self.AGV_2_go_from_one_to_another(instance_no, 'C', cur_node_2)
                    self.PA_condition.reserve_take_trayorpart()
                    # print("agv decide go to PA to take tray")
                    # print(self.PA_condition.tray_list)
                    # print(self.PA_condition.reserve_tray_num)
                    # print(self.PA_condition.rt_list) 
                    return is_waiting, cur_node_2
                elif index == 5:
                    cur_node_2 = 'PB'
                    self.AGV_2_go_from_one_to_another(instance_no, 'C', cur_node_2)
                    self.PB_condition.reserve_take_trayorpart()
                    return is_waiting, cur_node_2
                else:
                    cur_node_2 = 'D'
                    self.AGV_2_go_from_one_to_another(instance_no, 'C', cur_node_2)
                    self.D_in_condition.reserve_take_trayorpart()
                    return is_waiting, cur_node_2
            else:
                print("AGV_2_{} is waiting in C".format(instance_no-1))
                is_waiting = True
                return is_waiting, cur_node_2
        
        elif cur_node_2 == 'D':
            if self.AGV_2[instance_no-1].elec <= 20:
                # 若AGV带有托盘，则先放置托盘
                if self.AGV_2[instance_no-1].tray is not None:
                    self.AGV_2_put_tray(instance_no, 'D')
                else:
                    self.D_in_condition.cancel_reserve_after_take()
                # 若E2有空位置，则前往，否则原地等待
                if not self.E2.check_full():
                    self.AGV_go_E2(instance_no, cur_node_2)
                    cur_node_2 = 'E2'
                    return is_waiting, cur_node_2
                else:
                    print("E2 is full, AGV_2_{} is waiting in {}".format(instance_no-1))
                    is_waiting = True
                    return is_waiting, cur_node_2
            
            if self.AGV_2[instance_no-1].tray is None and last_waiting == None:
                if len(self.D_in_condition.tray_list) > 0:
                    if not self.PB_condition.check_full():
                        cur_node_2 = 'PB'
                        self.AGV_carry_partAndtray_from_D(instance_no, 'PB')
                        return is_waiting, cur_node_2
                    elif not self.C_condition.check_full():
                        cur_node_2 = 'C'
                        self.AGV_carry_partAndtray_from_D(instance_no, 'C')
                        return is_waiting, cur_node_2
                    else:
                        print("PB and C are full, AGV_2_{} waiting in D".format(instance_no-1))
                        self.D_in_condition.cancel_reserve_after_take()
                        is_waiting = True
                        return is_waiting, cur_node_2
                else:
                    print("No part and tray currently, AGV_2_{} waiting in D".format(instance_no-1))
                    self.D_in_condition.cancel_reserve_after_take()
                    is_waiting = True
                    return is_waiting, cur_node_2
            if last_waiting == None:
                self.AGV_2_put_tray(instance_no, 'D')
            # 拿物料前往PB
            if not self.PB_condition.check_full() and self.D_in_condition.check_out_pos_available() \
                and not self.D_in_condition.check_reserve_trayorpart_full():
                # print(self.D_in_condition.check_reserve_trayorpart_full())
                # print(self.D_in_condition.reserve_num)
                # print(self.D_in_condition.tray_list)
                waiting_time = self.D_in_condition.return_take_waiting_time()
                f1 = -self.t_D_PB*self.s_fac - max(0, waiting_time-self.t_D_PB)*self.t_fac + self.put_part1
                f2 = self.minus_inf
            # 拿物料前往C
            elif not self.C_condition.check_full() and self.D_in_condition.check_out_pos_available() \
                and not self.D_in_condition.check_reserve_trayorpart_full():
                waiting_time = max(self.D_in_condition.return_take_waiting_time()-self.total_time_recorder[1,instance_no-1]-self.t_C_D,0)
                f1 = self.minus_inf
                f2 = -self.t_C_D*self.s_fac - waiting_time*self.t_fac + self.put_part2
            else:
                f1 = self.minus_inf
                f2 = self.minus_inf
            # 前往SA拿物料
            if not self.SA_condition.check_reserve_full():
                waiting_time = max(0, (self.SA_condition.part_count+self.SA_condition.reserve_count)*self.part_freq-self.total_time_recorder[1,instance_no-1]-self.t_SA_D)
                f3 = -self.t_SA_D*self.s_fac - waiting_time*self.t_fac + self.take_part
            else:
                f3 = self.minus_inf
            # 前往PA拿托盘
            if not self.PA_condition.check_reserve_trayorpart_full() and not self.PA_condition.check_empty():
                waiting_time = max(self.PA_condition.waiting_time_calculate()-self.total_time_recorder[1,instance_no-1]-self.t_D_PA,0)
                f4 = -self.t_D_PA*self.s_fac - waiting_time*self.t_fac + self.take_part
            else:
                f4 = self.minus_inf
            # 前往PB拿托盘
            if not self.PB_condition.check_reserve_trayorpart_full() and not self.PB_condition.check_empty():
                waiting_time = max(self.PB_condition.waiting_time_calculate()-self.total_time_recorder[1,instance_no-1]-self.t_D_PB,0)
                f5 = -self.t_D_PB*self.s_fac - waiting_time*self.t_fac + self.take_part
            else:
                f5 = self.minus_inf
            # 前往C拿物料/托盘
            if not self.C_condition.check_reserve_trayorpart_full() and not self.C_condition.check_empty():
                f6 = -self.t_C_D*self.s_fac + self.take_part
            else:
                f6 = self.minus_inf 
            f_list.extend((f1, f2, f3, f4, f5, f6))
            print(f_list)
            print("In D, check PB reserve tray full {}".format(self.PB_condition.check_reserve_trayorpart_full()))
            print("In D, check PB tray {}".format(self.PB_condition.tray_list))
            print("In D, check PB reserve tray num {}".format(self.PB_condition.reserve_tray_num))
            index = f_list.index(max(f_list))
            if max(f_list) != self.minus_inf:
                is_waiting = False
                if index == 0:
                    self.D_in_condition.reserve_take_trayorpart()
                    cur_node_2 = 'PB'
                    self.AGV_carry_partAndtray_from_D(instance_no, 'PB')
                    # print(self.D_in_condition.tray_list)
                    # print(self.D_in_condition.oc_list)
                    # print(self.D_in_condition.reserve_tray_num)
                    return is_waiting, cur_node_2
                elif index == 1:
                    self.D_in_condition.reserve_take_trayorpart()
                    cur_node_2 = 'C'
                    self.AGV_carry_partAndtray_from_D(instance_no, 'C')
                    return is_waiting, cur_node_2
                elif index == 2:
                    cur_node_2 = 'SA'
                    self.AGV_2_go_from_one_to_another(instance_no, 'D', cur_node_2)
                    return is_waiting, cur_node_2
                elif index == 3:
                    cur_node_2 = 'PA'
                    self.AGV_2_go_from_one_to_another(instance_no, 'D', cur_node_2)
                    self.PA_condition.reserve_take_trayorpart()
                    # print("agv decide to go to PA")
                    # print(self.PA_condition.tray_list)
                    # print(self.PA_condition.reserve_tray_num)
                    # print(self.PA_condition.rt_list) 
                    return is_waiting, cur_node_2
                elif index == 4:
                    cur_node_2 = 'PB'
                    self.AGV_2_go_from_one_to_another(instance_no, 'D', cur_node_2)
                    self.PB_condition.reserve_take_trayorpart()
                    return is_waiting, cur_node_2
                else:
                    cur_node_2 = 'C'
                    self.AGV_2_go_from_one_to_another(instance_no, 'D', cur_node_2)
                    self.C_condition.reserve_take_trayorpart()
                    return is_waiting, cur_node_2
            else:
                print("AGV_2_{} is waiting in D".format(instance_no-1))
                is_waiting = True
                return is_waiting, cur_node_2

        # 在E2充电并决策前往其他点位
        elif cur_node_2 == 'E2':
            self.E2.cancel_reserve_after_reach()
            # 前往SA拿新的物料
            if not self.SA_condition.check_reserve_full():
                waiting_time = max(0, (self.SA_condition.part_count+self.SA_condition.reserve_count)*self.part_freq-self.total_time_recorder[1,instance_no-1]-self.t_SA_E2)
                f1 = -self.t_SA_E2*self.s_fac - waiting_time*self.t_fac + self.take_part
            else:
                f1 = self.minus_inf
            # 前往PA拿托盘
            if not self.PA_condition.check_reserve_trayorpart_full() and not self.PA_condition.check_empty():
                # print(self.PA_condition.oc_list)
                # print(self.PA_condition.tray_list)
                # print(self.PA_condition.rt_list)
                waiting_time = max(self.PA_condition.waiting_time_calculate()-self.total_time_recorder[1,instance_no-1]-self.t_PA_E2,0)
                f2 = -self.t_PA_E2*self.s_fac - waiting_time*self.t_fac + self.take_part
            else:
                f2 = self.minus_inf
            # 前往PB拿托盘
            if not self.PB_condition.check_reserve_trayorpart_full() and not self.PB_condition.check_empty():
                waiting_time = max(self.PB_condition.waiting_time_calculate()-self.total_time_recorder[1,instance_no-1]-self.t_PB_E2,0)
                f3 = -self.t_PB_E2*self.s_fac - waiting_time*self.t_fac + self.take_part
            else:
                f3= self.minus_inf
            # 前往D拿物料
            if self.D_in_condition.check_out_pos_available() and not self.D_in_condition.check_reserve_trayorpart_full():
                waiting_time = max(self.D_in_condition.return_take_waiting_time()-self.total_time_recorder[1,instance_no-1]-self.t_D_E2,0)
                f4 = -self.t_D_E2*self.s_fac - waiting_time*self.t_fac + self.take_part
            else:
                f4 = self.minus_inf
            # 前往C拿物料/托盘
            if not self.C_condition.check_reserve_trayorpart_full() and not self.C_condition.check_empty():
                f5 = -self.t_C_E2*self.s_fac + self.take_part
            else:
                f5 = self.minus_inf 
            f_list.extend((f1, f2, f3, f4, f5))
            # print(f_list)
            index = f_list.index(max(f_list))
            if index == 0:
                cur_node_2 = 'SA'
                self.AGV_go_from_E2(instance_no, cur_node_2)
                return is_waiting, cur_node_2
            elif index == 1:
                cur_node_2 = 'PA'
                self.AGV_go_from_E2(instance_no, cur_node_2)
                self.PA_condition.reserve_take_trayorpart()
                return is_waiting, cur_node_2
            elif index == 2:
                cur_node_2 = 'PB'
                self.AGV_go_from_E2(instance_no, cur_node_2)
                self.PB_condition.reserve_take_trayorpart()
                return is_waiting, cur_node_2
            elif index == 3:
                cur_node_2 = 'D'
                self.AGV_go_from_E2(instance_no, cur_node_2)
                self.D_in_condition.reserve_take_trayorpart()
                # print(self.D_in_condition.reserve_tray_num)
                # print(self.D_in_condition.tray_list)
                # print(self.D_in_condition.out_pos_available)
                return is_waiting, cur_node_2
            else:
                cur_node_2 = 'C'
                self.AGV_go_from_E2(instance_no, cur_node_2)
                self.C_condition.reserve_take_trayorpart()
                return is_waiting, cur_node_2
                

    # 区域一AGV运动逻辑        
    def AGV_region_1(self, instance_no, cur_node_1):
        # if self.check_finish(): 
        is_waiting = False

        if cur_node_1 == 'SB':
            if self.AGV_1[instance_no-1].elec <= 20:
                # 若AGV带有托盘，则先回收托盘
                if self.AGV_1[instance_no-1].tray is not None:
                    self.AGV_put_tray_on_SB(instance_no)
                # 若E1有空位置，则前往，否则原地等待
                if not self.E1.check_full():
                    cur_node_1 = self.AGV_go_E1(instance_no, cur_node_1)
                    is_waiting = False
                    return is_waiting, cur_node_1
                else:
                    print("E1 is full, AGV_1_{} is waiting in {}".format(instance_no-1, cur_node_1))
                    is_waiting = True
                    return is_waiting, cur_node_1
            # 若AGV携带托盘且电量足够，先放置托盘
            if self.AGV_1[instance_no-1].tray is not None:
                self.AGV_put_tray_on_SB(instance_no)
            # AGV处于空载状态，先看SB有无物料或托盘，若有，则先搬运物料
            if len(self.SB_condition.parts_SB) > 0 and len(self.SB_condition.SB_tray) > 0 and self.D_in_condition.check_in_pos_available() \
                and not self.D_in_condition.check_full():      
                cur_node_1 = self.AGV_wait_and_carry_partAndtray_from_SB_to_D(instance_no)
                is_waiting = False
                return is_waiting, cur_node_1
            # 再看D有无需要搬运的托盘
            elif self.D_out_condition.check_out_pos_available() and not self.D_out_condition.check_reserve_trayorpart_full():
                self.AGV_1_go_from_one_to_another(instance_no, 'SB', 'D')
                self.D_out_condition.reserve_take_trayorpart()
                is_waiting = False
                cur_node_1 = 'D'
                return is_waiting, cur_node_1
            else:
                print('AGV_1_{} No part or tray in SB now, no tray in D now, is waiting'.format(instance_no-1))
                is_waiting = True
                return is_waiting, cur_node_1

        elif cur_node_1 == 'D':
            if self.AGV_1[instance_no-1].elec <= 20:
                # 若AGV带有物料，则先放置物料
                if self.AGV_1[instance_no-1].part is not None:
                    self.AGV_put_partAndtray_on_D(instance_no)
                # 若E1有空位置，则前往，否则原地等待
                if not self.E1.check_full():
                    cur_node_1 = self.AGV_go_E1(instance_no, cur_node_1)
                    is_waiting = False
                    return is_waiting, cur_node_1
                else:
                    print("E1 is full, AGV_1_{} is waiting in D".format(instance_no-1))
                    is_waiting = True
                    return is_waiting, cur_node_1
            # AGV若空载前来，先看有无托盘需要搬运，否则等待
            if self.AGV_1[instance_no-1].part is None:
                if self.D_out_condition.check_out_pos_available() and not self.D_out_condition.check_reserve_trayorpart_full():
                    self.AGV_carry_tray_from_D_to_SB(instance_no)
                    cur_node_1 = 'SB'
                    is_waiting = False
                    return is_waiting, cur_node_1
                else:
                    print("AGV_1_{} No tray in D currently, please waiting".format(instance_no-1))
                    is_waiting = True
                    return is_waiting, cur_node_1
            # AGV负载前来，先放物料，再看D有无托盘，若无，则等待
            else:
                self.AGV_put_partAndtray_on_D(instance_no)
                if self.D_out_condition.check_out_pos_available() and not self.D_out_condition.check_reserve_trayorpart_full():
                    self.D_out_condition.reserve_take_trayorpart()
                    self.AGV_carry_tray_from_D_to_SB(instance_no)
                    cur_node_1 = 'SB'
                    is_waiting = False
                    return is_waiting, cur_node_1
                else:
                    print("AGV_1_{} No tray in D currently, please waiting".format(instance_no-1))
                    is_waiting = True
                    return is_waiting, cur_node_1
        
        # AGV在E1充电，电满后，若D有空托盘，先去D，若无再返回SB
        else:
            self.E1.cancel_reserve_after_reach()
            # print(self.D_out_condition.tray_list)
            # print(self.D_out_condition.reserve_tray_num)
            # print(self.D_out_condition.check_out_pos_available())
            # print(self.D_out_condition.check_reserve_trayorpart_full())
            if self.D_out_condition.check_out_pos_available() and not self.D_out_condition.check_reserve_trayorpart_full():
                self.AGV_go_from_E1(instance_no, 'D')
                self.D_out_condition.reserve_take_trayorpart()
                cur_node_1 = 'D'
                is_waiting = False
            else:
                self.AGV_go_from_E1(instance_no, 'SB')
                cur_node_1 = 'SB'
                is_waiting = False
            return is_waiting, cur_node_1

    # 需要保证时间队列里面不能有相同的时间元素，如果正好有，则加上一个很小的随机扰动
    def time_correction(self, list, time):
        if list.count(time) != 0:
            time_1 = time + np.random.randint(0,20) - 10
            while list.count(time_1) != 0:
                time_1 = time + np.random.randint(0,20) - 10
            list.append(time_1)
            return time_1, list
        else:
            list.append(time)
            return time, list

    # 仿真初始化
    def Simulation_initialize(self):
        for i in range(self.num_AGV_1):
            node = 'SB'
            is_waiting, node = self.AGV_region_1(i+1, node)
        for i in range(self.num_AGV_2):
            is_waiting, node = self.AGV_region_2(i+1, 'SA')

    # 仿真过程
    def Simulation_process(self):
        self.Simulation_initialize()
        while not self.check_finish():
            # pop出时间序列中最终结束动作最短的
            print(self.agv_action_buffer)
            print(self.time_queue)
            print(self.waiting_list_2)
            print(self.waiting_list_1)
            self.time_queue.sort()
            time = self.time_queue.pop(0)
            # 输出该时间对应的AGV的动作并删除字典中的存储
            message = self.agv_action_buffer[time]['action']
            agv_location = self.agv_action_buffer[time]['location']
            node = self.agv_action_buffer[time]['node']
            print("output message: " + message)
            file.write(message)
            del self.agv_action_buffer[time]
            # 输出动作的AGV继续决策，放入buffer
            if agv_location[0] == 1:
                is_waiting, node = self.AGV_region_1(agv_location[1], node)
                if is_waiting:
                    self.waiting_list_1[agv_location[1]-1] = node
            else:
                is_waiting, node = self.AGV_region_2(agv_location[1], node)
                if is_waiting:
                    self.waiting_list_2[agv_location[1]-1] = node
            # 查看waiting_list中是否有正在等待的车可以继续执行任务
            # print(self.waiting_list_1)
            for i, item in enumerate(self.waiting_list_1):
                if item != None:
                    self.total_time_recorder[0,i] = time
                    is_waiting, node = self.AGV_region_1(i+1, item)
                    if not is_waiting:
                        self.waiting_list_1[i] = None
            for i, item in enumerate(self.waiting_list_2):
                if item != None:
                    self.total_time_recorder[1,i] = time
                    is_waiting, node = self.AGV_region_2(i+1, item)
                    if not is_waiting:
                        self.waiting_list_2[i] = None

file = open('多AGV场景仿真输出.txt', mode = 'w')
solver = ProductionWorld()
solver.Simulation_process()
file.close()
