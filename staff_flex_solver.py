"""Configurable staffing coverage and daily availability models."""
import numpy as np
from scipy.optimize import milp, linprog, Bounds, LinearConstraint


def solve(config):
    days = int(config['days'])
    if not 1 <= days <= 14:
        raise ValueError('排班天数须为 1–14')
    rule = str(config['rule'])
    if rule == 'individual':
        return _individual(config, days)
    if rule not in {'flex', 'repeat', 'consecutive'}:
        raise ValueError('未知排班规则')
    slots = int(config['slots'])
    length = int(config['shift_slots'])
    if not 1 <= slots <= 12 or not 1 <= length <= slots:
        raise ValueError('每天时段数须为 1–12，班次长度须在 1 与时段数之间')
    demand = np.asarray(config['demand'], dtype=float)
    if demand.shape != (days, slots) or not np.isfinite(demand).all() or (demand < 0).any() or not np.all(demand == np.floor(demand)):
        raise ValueError(f'需求须为 {days} 行、每行 {slots} 个非负整数')
    workdays = int(config.get('workdays', 1))
    if rule == 'consecutive' and not 1 <= workdays <= days:
        raise ValueError('连续工作天数须在 1 与排班天数之间')
    if rule != 'consecutive':
        workdays = 1

    # A variable means staff starting at a day/slot. The planning horizon
    # repeats cyclically, so overnight shifts and weekly rotation are explicit.
    starts = [(0, s) for s in range(slots)] if rule == 'repeat' else [(d, s) for d in range(days) for s in range(slots)]
    total = days * slots
    A = np.zeros((total, len(starts)), dtype=float)
    for col, (day, slot) in enumerate(starts):
        origins = range(days) if rule == 'repeat' else ((day + offset) % days for offset in range(workdays))
        for origin in origins:
            for offset in range(length):
                A[((origin * slots + slot + offset) % total), col] += 1
    result = milp(np.ones(len(starts)), integrality=np.ones(len(starts)),
                  bounds=Bounds(np.zeros(len(starts)), np.full(len(starts), np.inf)),
                  constraints=LinearConstraint(A, demand.ravel(), np.full(total, np.inf)),
                  options={'time_limit': 20})
    if result.x is None or result.status != 0:
        raise ValueError('求解器未找到最优排班；请检查需求或缩小规模')
    counts = np.rint(result.x).astype(int)
    coverage = (A @ counts).reshape(days, slots).astype(int)
    schedule = [{'day': d + 1, 'slot': s + 1, 'people': int(counts[i])}
                for i, (d, s) in enumerate(starts) if counts[i] > 0]
    return {'rule': rule, 'days': days, 'slots': slots, 'shift_slots': length,
            'workdays': workdays, 'value': int(counts.sum()),
            'unit': '总人次' if rule == 'flex' else '固定班组人数' if rule == 'repeat' else '员工人数',
            'schedule': schedule, 'coverage': coverage.tolist(),
            'demand': demand.astype(int).tolist(),
            'note': '按设定周期循环；跨日班次可覆盖次日时段。'}


def _individual(config, days):
    demand = np.asarray(config['daily_hours'], dtype=float)
    people = config['people']
    if demand.shape != (days,) or not np.isfinite(demand).all() or (demand < 0).any():
        raise ValueError(f'每日总需求须为 {days} 个非负工时')
    if not isinstance(people, list) or not 1 <= len(people) <= 30:
        raise ValueError('请填写 1–30 名人员')
    names = [str(p['name']).strip() for p in people]
    if any(not n for n in names) or len(set(names)) != len(names):
        raise ValueError('人员名称必须唯一且非空')
    n = len(people)
    wages = np.asarray([p['wage'] for p in people], dtype=float)
    minimum = np.asarray([p['minimum'] for p in people], dtype=float)
    available = np.asarray([p['available'] for p in people], dtype=float)
    if available.shape != (n, days) or not np.isfinite(available).all() or (available < 0).any():
        raise ValueError(f'每人须提供 {days} 天的非负可用工时')
    if not np.isfinite(wages).all() or not np.isfinite(minimum).all() or (wages < 0).any() or (minimum < 0).any():
        raise ValueError('工资和最低工时须为非负数')
    A_eq = np.zeros((days, n * days))
    for d in range(days):
        A_eq[d, np.arange(n) * days + d] = 1
    A_ub = np.zeros((n, n * days))
    for i in range(n):
        A_ub[i, i * days:(i + 1) * days] = -1
    result = linprog(np.repeat(wages, days), A_ub=np.vstack((A_ub, -A_eq)),
                     b_ub=np.concatenate((-minimum, -demand)),
                     bounds=[(0, float(x)) for x in available.ravel()], method='highs')
    if not result.success:
        raise ValueError('当前可用时间和最低工时无法满足每日需求')
    hours = result.x.reshape(n, days)
    return {'rule': 'individual', 'days': days, 'value': round(float(result.fun), 3),
            'unit': '工资成本', 'names': names, 'hours': np.round(hours, 3).tolist(),
            'daily_hours': demand.tolist(), 'note': '结果是每日工时分配，不代表具体钟点。'}
