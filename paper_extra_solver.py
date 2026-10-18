"""Deterministic solvers for scheduling-adjacent COOPA benchmark cases."""
from itertools import permutations
import numpy as np
from scipy.optimize import linprog, milp, Bounds, LinearConstraint

DEFAULTS={
 'IndustryOR-035':{'times':[[3,1,1],[2,1.5,1],[3,1.2,1.3],[2,2,2],[2.1,2,3]]},
 'IndustryOR-074':{'tasks':[{'id':'A','duration':4,'pred':[]},{'id':'B','duration':3,'pred':['A']}],'daily_cost':1000,'rental_cost':5000,'rental_start':'A','rental_end':'B'},
 'BWOR-053':{'wages':[10,10,9.9,9.8,10.8,11.3],'available':[[6,0,9,0,7],[0,9,0,6,0],[4,8,3,0,5],[5,5,6,0,4],[3,0,4,8,0],[0,9,0,6,3]],'daily_hours':14,'weekly_min':[8,8,8,8,7,7]},
 'BWOR-079':{'demand':[18,20,19,17,12]},
 'ComplexLP-179':{'demand':[2,4,4,3,1,2,3]},
 'ComplexLP-180':{'demand':[5,4,7,3,8,4,3]},
}

def industry35(config):
    p=np.array(config['times'],dtype=float)
    if p.ndim!=2 or not 2<=p.shape[1]<=4 or not 1<=len(p)<=8 or not np.isfinite(p).all() or (p<=0).any():raise ValueError('工时须为 1–8 行、每行 2–4 个正数')
    best=None
    for seq in permutations(range(len(p))):
        free=np.zeros(p.shape[1]); tasks=[]
        for j in seq:
            for k in range(p.shape[1]):
                st=max(free[k],free[k-1] if k else 0)
                free[k]=st+p[j,k]
                tasks.append({'job':j+1,'machine':k+1,'start':round(st,3),'end':round(free[k],3)})
        if best is None or free[-1]<best['value']-1e-9:best={'value':round(float(free[-1]),3),'order':[x+1 for x in seq],'tasks':tasks}
    return {'case':'IndustryOR-035','objective':'最小总完工时间（小时）','gold':14.1,**best}

def industry74(config):
    tasks=config['tasks']
    if not isinstance(tasks,list) or not 1<=len(tasks)<=30:raise ValueError('请提供 1–30 个活动')
    names=[str(t['id']).strip() for t in tasks]
    if any(not n for n in names) or len(set(names))!=len(names):raise ValueError('活动名称应唯一且非空')
    d=np.array([t['duration'] for t in tasks],float)
    if not np.isfinite(d).all() or (d<=0).any():raise ValueError('活动时长须为正数')
    daily=float(config['daily_cost']);rental_rate=float(config['rental_cost'])
    if not np.isfinite([daily,rental_rate]).all() or min(daily,rental_rate)<0:raise ValueError('成本须为非负数')
    first=str(config['rental_start']);last=str(config['rental_end'])
    if first not in names or last not in names:raise ValueError('租赁起止活动必须存在')
    n=len(tasks);rows=[];rhs=[]
    for t in tasks:
        b=names.index(t['id'])
        for a_name in t['pred']:
            if a_name not in names or a_name==t['id']:raise ValueError('前置活动不存在或指向自己')
            a=names.index(a_name);r=np.zeros(n+1);r[a]=1;r[b]=-1;rows.append(r);rhs.append(-d[a])
    for i in range(n):
        r=np.zeros(n+1);r[i]=1;r[n]=-1;rows.append(r);rhs.append(-d[i])
    # Rental end must follow rental start, including the start activity duration.
    r=np.zeros(n+1);r[names.index(first)]=1;r[names.index(last)]=-1;rows.append(r);rhs.append(-d[names.index(first)])
    c=np.zeros(n+1);c[n]=daily;c[names.index(last)]+=rental_rate;c[names.index(first)]-=rental_rate
    res=linprog(c,A_ub=rows,b_ub=rhs,bounds=[(0,None)]*(n+1),method='highs')
    if not res.success:raise ValueError(res.message)
    x=res.x;rental=x[names.index(last)]+d[names.index(last)]-x[names.index(first)]
    return {'case':'IndustryOR-074','objective':'最小项目工期成本加设备租赁成本','value':round(float(daily*x[n]+rental_rate*rental),3),'duration':round(float(x[n]),3),'rental_days':round(float(rental),3),'starts':{name:round(float(x[i]),3) for i,name in enumerate(names)},'activities':{name:float(d[i]) for i,name in enumerate(names)}}

def weekly_lp(demand,case,gold):
    A=np.zeros((7,7))
    for day in range(7):
        for offset in range(5):A[day,(day-offset)%7]=1
    res=linprog(np.ones(7),A_ub=-A,b_ub=-np.array(demand),bounds=[(0,None)]*7,method='highs')
    if not res.success:raise ValueError(res.message)
    return {'case':case,'objective':'连续松弛的最低排班人数','value':round(float(res.fun),6),'rounded':int(np.floor(res.fun+0.5)),'starts':[round(float(x),6) for x in res.x],'coverage':[round(float(x),6) for x in A@res.x],'demand':demand,'integrality':False}

def bwor53(config):
    wage=np.array(config['wages'],float)
    cap=np.array(config['available'],float)
    minimum=np.array(config['weekly_min'],float)
    daily=float(config['daily_hours'])
    n=len(wage)
    if not 1<=n<=20 or cap.shape!=(n,5) or minimum.shape!=(n,) or not np.isfinite(wage).all() or not np.isfinite(cap).all() or not np.isfinite(minimum).all() or not np.isfinite(daily) or min(wage.min(),cap.min(),minimum.min(),daily)<0:raise ValueError('人员值班数据维度或数值无效')
    c=np.repeat(wage,5);Aeq=np.zeros((5,n*5))
    for day in range(5):Aeq[day,day::5]=1
    Aub=np.zeros((n,n*5))
    for i in range(n):Aub[i,i*5:(i+1)*5]=-1
    res=linprog(c,A_ub=Aub,b_ub=-minimum,A_eq=Aeq,b_eq=np.full(5,daily),bounds=[(0,float(v)) for v in cap.flatten()],method='highs')
    if not res.success:raise ValueError(res.message)
    return {'case':'BWOR-053','objective':'最低周工资（元）','value':round(float(res.fun),4),'hours':np.round(res.x.reshape(n,5),4).tolist(),'students':list(range(1,n+1)),'days':['周一','周二','周三','周四','周五'],'note':'结果是每天工时分配，不推断连续值班的具体时钟段。'}

def bwor79(config):
    # Literal interpretation: a start-day cohort works shifts 1..5 on five consecutive days.
    # Night demand applies to both 22-02 (shift 5 only) and 02-06 (shift 1 only).
    demand=np.array(config['demand'],float)
    if demand.shape!=(5,) or not np.isfinite(demand).all() or (demand<0).any():raise ValueError('需求须为 5 个非负数')
    rows=[];rhs=[]
    for day in range(7):
        sh=np.zeros((5,7))
        for j in range(5):sh[j,(day-j)%7]=1
        for js,need in [([0,1],demand[0]),([1,2],demand[1]),([2,3],demand[2]),([3,4],demand[3]),([4],demand[4]),([0],demand[4])]:rows.append(sum(sh[j] for j in js));rhs.append(need)
    A=np.array(rows);res=milp(np.ones(7),integrality=np.ones(7),bounds=Bounds(np.zeros(7),np.full(7,np.inf)),constraints=LinearConstraint(A,np.array(rhs),np.full(len(rhs),np.inf)),options={'time_limit':20})
    if res.x is None:raise ValueError('跨周整数排班未找到解')
    return {'case':'BWOR-079','objective':'五日轮班规则所需最低人数','value':int(round(res.fun)),'start_day_cohorts':[int(round(x)) for x in res.x],'note':'夜间 22:00–06:00 的两个半段均要求覆盖；各起始日的人数为整数。'}

def solve(case,config=None):
    if case not in DEFAULTS:raise ValueError('未知场景')
    original=DEFAULTS[case]
    config=original if config is None else config
    if not isinstance(config,dict) or set(config)!=set(original):raise ValueError('参数字段须与示例一致')
    if case=='IndustryOR-035':out=industry35(config)
    elif case=='IndustryOR-074':out=industry74(config)
    elif case=='BWOR-053':out=bwor53(config)
    elif case=='BWOR-079':out=bwor79(config)
    else:
        demand=config['demand']
        if len(demand)!=7 or any(not isinstance(x,(int,float)) or x<0 or x>1000 for x in demand):raise ValueError('周需求须为 7 个非负数')
        out=weekly_lp(demand,case,4 if case.endswith('179') else 8)
    out['benchmark_match']=config==original
    return out

if __name__=='__main__':
    import json
    for name in DEFAULTS:
        try:print(name,json.dumps(solve(name),ensure_ascii=False))
        except Exception as exc:print(name,'ERROR',exc)
