/*
 * ========================================================================
 *  课程设计2026 - 任务控制块(TCB)结构定义
 *  使用UCOS-II实现周期实时任务抢占式调度（教材P94）
 * ========================================================================
 *
 *  任务参数说明（对应教材图3-10）：
 *    任务A：周期 Ta = 20ms,  计算时间 Ca = 10ms, 截止时间 Da = 20ms
 *    任务B：周期 Tb = 50ms,  计算时间 Cb = 25ms, 截止时间 Db = 50ms
 *
 *  实际运行时按比例放大到 2s 和 5s（x100倍），便于观察显示效果。
 *  也可以调整 SCALE_FACTOR 缩放比例。
 */

#ifndef __TASK_TCB_H__
#define __TASK_TCB_H__

#include <ucos_ii.h>

/* ---- 缩放比例：教材中为ms级，实际显示放大到s级 ---- */
#define SCALE_FACTOR    100     /* 20ms*100=2000ms=2s, 50ms*100=5000ms=5s */

/* ---- 任务参数（原始值，单位ms） ---- */
#define TASK_A_PERIOD       20      /* 任务A周期 */
#define TASK_A_COMPUTE      10      /* 任务A计算时间 */
#define TASK_A_DEADLINE     20      /* 任务A截止时间 */

#define TASK_B_PERIOD       50      /* 任务B周期 */
#define TASK_B_COMPUTE      25      /* 任务B计算时间 */
#define TASK_B_DEADLINE     50      /* 任务B截止时间 */

/* ---- 实际运行参数（缩放后，单位ms -> tick数） ---- */
#define TASK_A_PERIOD_TICKS     (TASK_A_PERIOD  * SCALE_FACTOR / 10)  /* 2s  = 200 ticks@100Hz */
#define TASK_A_COMPUTE_TICKS    (TASK_A_COMPUTE * SCALE_FACTOR / 10)  /* 1s  = 100 ticks */
#define TASK_A_DEADLINE_TICKS   (TASK_A_DEADLINE* SCALE_FACTOR / 10)  /* 2s  = 200 ticks */

#define TASK_B_PERIOD_TICKS     (TASK_B_PERIOD  * SCALE_FACTOR / 10)  /* 5s  = 500 ticks */
#define TASK_B_COMPUTE_TICKS    (TASK_B_COMPUTE * SCALE_FACTOR / 10)  /* 2.5s= 250 ticks */
#define TASK_B_DEADLINE_TICKS   (TASK_B_DEADLINE* SCALE_FACTOR / 10)  /* 5s  = 500 ticks */

/* ---- 任务优先级 ---- */
#define TASK_A_PRIO             5
#define TASK_B_PRIO             6
#define TASK_TICK_SERVICE_PRIO  3   /* 时间片中断服务任务 优先级最高 */

/* ---- 任务栈大小 ---- */
#define TASK_STK_SIZE           256

/* ======================================================================
 *  PCB / TCB 结构定义
 *  在UCOS-II原生OS_TCB基础上扩展实时调度所需字段
 * ====================================================================== */
typedef struct {
    /* ---- UCOS-II 原生 TCB 字段 ---- */
    OS_STK        *OSTCBStkPtr;       /* 指向任务栈顶 */
    OS_STK        *OSTCBStkBase;      /* 指向任务栈底（用于统计） */
    INT16U         OSTCBStkSize;      /* 任务栈大小 */

    /* ---- 扩展：周期实时任务调度字段（PCB/TCB） ---- */
    INT8U          OSTCBPrio;         /* 任务优先级 */
    INT8U          OSTCBStat;         /* 任务状态 */

    /* 时间参数（单位：tick数） */
    INT32U         Period;            /* 任务周期 */
    INT32U         ComputeTime;       /* 计算时间（最坏情况执行时间WCET） */
    INT32U         Deadline;          /* 绝对截止时间 */
    INT32U         RelativeDeadline;  /* 相对截止时间（= 周期） */

    /* 调度运行时参数 */
    INT32U         RemainingTime;     /* 剩余计算时间 */
    INT32U         NextArrivalTime;   /* 下一次到达时间 */
    INT32U         AbsoluteDeadline;  /* 当前周期的绝对截止时间 */

    /* 任务标识 */
    INT8U          TaskID;            /* 任务ID: 1=A, 2=B */
    char           TaskName[4];       /* 任务名称显示 */

    /* 统计信息 */
    INT32U         ExecCount;         /* 已执行tick数 */
    INT32U         MissCount;         /* 错过截止时间次数 */
    BOOLEAN        IsActive;          /* 任务是否在当前周期内活跃 */
} RT_TCB;

/* ======================================================================
 *  全局变量声明
 * ====================================================================== */
extern RT_TCB  TCB_TaskA;            /* 任务A的TCB */
extern RT_TCB  TCB_TaskB;            /* 任务B的TCB */

extern OS_STK  TaskA_Stk[TASK_STK_SIZE];
extern OS_STK  TaskB_Stk[TASK_STK_SIZE];
extern OS_STK  TickService_Stk[TASK_STK_SIZE];

/* ======================================================================
 *  函数声明
 * ====================================================================== */
void  RT_TCB_Init(RT_TCB *tcb, INT8U prio, INT8U taskID,
                  INT32U period, INT32U computeTime, INT32U deadline,
                  char *name);

void  TaskA(void *pdata);
void  TaskB(void *pdata);
void  TickServiceTask(void *pdata);

void  App_TimeTickHook(void);
void  EDF_Schedule(void);
void  DisplayOutput(INT8U taskID);

#endif /* __TASK_TCB_H__ */
