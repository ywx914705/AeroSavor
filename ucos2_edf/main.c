/*
 * ========================================================================
 *  课程设计2026 - UCOS-II周期实时任务抢占式调度（EDF算法）
 *  教材P94 - 图3-10 EDF算法用于抢占式调度方式之例
 * ========================================================================
 *
 *  设计说明：
 *  本程序基于UCOS-II实时操作系统，实现了EDF（Earliest Deadline First，
 *  最早截止时间优先）抢占式调度算法，用于调度周期实时任务。
 *
 *  硬件环境：以ARM Cortex-M3为例（可移植到其他UCOS-II支持的平台）
 *  软件环境：UCOS-II v2.86+
 *
 *  任务说明：
 *  - 任务A：周期2s，在屏幕上显示"A"
 *  - 任务B：周期5s，在屏幕上显示"B"
 *  - 时间片中断服务：负责EDF调度决策
 *
 *  EDF调度原理（教材图3-10）：
 *  在每个调度时刻，比较所有就绪任务的绝对截止时间，
 *  选择截止时间最早的任务运行。当新任务到达时，如果新任务
 *  的截止时间比当前运行任务更早，则发生抢占。
 *
 *  时间线示例（教材）：
 *  t=0:   A1到达(deadline=20), B1到达(deadline=50) -> 运行A1
 *  t=10:  A1完成 -> 运行B1
 *  t=20:  A2到达(deadline=40) < B1截止(50) -> 抢占B1, 运行A2
 *  t=30:  A2完成 -> 恢复B1
 *  t=40:  A3到达(deadline=60), B1截止(50)<A3 -> 继续B1
 *  t=45:  B1完成 -> 运行A3
 *  ......
 */

#include <stdio.h>
#include <string.h>
#include <ucos_ii.h>
#include "app_cfg.h"

/* ======================================================================
 *  全局变量
 * ====================================================================== */

/* 两个周期实时任务的TCB结构 */
RT_TCB  TCB_TaskA;
RT_TCB  TCB_TaskB;

/* 任务栈 */
OS_STK  TaskA_Stk[TASK_STK_SIZE];
OS_STK  TaskB_Stk[TASK_STK_SIZE];
OS_STK  TickService_Stk[TASK_STK_SIZE];

/* 全局时钟计数器（tick数） */
volatile INT32U  SystemTickCounter = 0;

/* 调度日志（用于调试和报告） */
#define LOG_SIZE  128
typedef struct {
    INT32U time;
    INT8U  fromTask;
    INT8U  toTask;
    INT8U  reason;  /* 0=完成, 1=抢占, 2=新到达 */
} ScheduleLog;

ScheduleLog  SchedLog[LOG_SIZE];
INT32U       SchedLogIdx = 0;

/* ======================================================================
 *  TCB初始化函数
 *  功能：初始化任务控制块的所有字段
 * ====================================================================== */
void RT_TCB_Init(RT_TCB *tcb, INT8U prio, INT8U taskID,
                 INT32U period, INT32U computeTime, INT32U deadline,
                 char *name)
{
    /* UCOS-II 原生字段 */
    tcb->OSTCBStkPtr    = (OS_STK *)0;
    tcb->OSTCBStkSize   = TASK_STK_SIZE;
    tcb->OSTCBPrio      = prio;
    tcb->OSTCBStat      = OS_STAT_RDY;

    /* 实时调度参数 */
    tcb->Period         = period  * SCALE_FACTOR / 10;
    tcb->ComputeTime    = computeTime * SCALE_FACTOR / 10;
    tcb->Deadline       = deadline * SCALE_FACTOR / 10;
    tcb->RelativeDeadline = tcb->Period;

    /* 运行时参数 */
    tcb->RemainingTime  = 0;
    tcb->NextArrivalTime = 0;
    tcb->AbsoluteDeadline = tcb->Deadline;
    tcb->IsActive       = FALSE;

    /* 任务标识 */
    tcb->TaskID         = taskID;
    strncpy(tcb->TaskName, name, 3);
    tcb->TaskName[3] = '\0';

    /* 统计 */
    tcb->ExecCount      = 0;
    tcb->MissCount      = 0;
}

/* ======================================================================
 *  EDF调度算法实现
 *  功能：在每个时间片中断时，选择绝对截止时间最早的任务运行
 *
 *  算法步骤：
 *  1. 检查是否有新任务到达
 *  2. 比较所有活跃任务的绝对截止时间
 *  3. 选择截止时间最早的任务
 *  4. 如果选中的不是当前任务，触发上下文切换（抢占）
 * ====================================================================== */
void EDF_Schedule(void)
{
    RT_TCB *pTaskA = &TCB_TaskA;
    RT_TCB *pTaskB = &TCB_TaskB;
    RT_TCB *pSelected = NULL;
    INT8U   fromPrio, toPrio;

    INT32U currentTick = SystemTickCounter;

    /* ---- 第1步：检查任务到达 ---- */

    /* 检查任务A是否到达新周期 */
    if (currentTick >= pTaskA->NextArrivalTime) {
        if (pTaskA->RemainingTime <= 0 || !pTaskA->IsActive) {
            /* 任务A的新周期开始 */
            pTaskA->IsActive = TRUE;
            pTaskA->RemainingTime = pTaskA->ComputeTime;
            pTaskA->AbsoluteDeadline = currentTick + pTaskA->Deadline;
            pTaskA->NextArrivalTime = currentTick + pTaskA->Period;
        }
    }

    /* 检查任务B是否到达新周期 */
    if (currentTick >= pTaskB->NextArrivalTime) {
        if (pTaskB->RemainingTime <= 0 || !pTaskB->IsActive) {
            /* 任务B的新周期开始 */
            pTaskB->IsActive = TRUE;
            pTaskB->RemainingTime = pTaskB->ComputeTime;
            pTaskB->AbsoluteDeadline = currentTick + pTaskB->Deadline;
            pTaskB->NextArrivalTime = currentTick + pTaskB->Period;
        }
    }

    /* ---- 第2步：EDF选择 - 比较绝对截止时间 ---- */
    if (pTaskA->IsActive && pTaskA->RemainingTime > 0) {
        pSelected = pTaskA;
    }
    if (pTaskB->IsActive && pTaskB->RemainingTime > 0) {
        if (pSelected == NULL) {
            pSelected = pTaskB;
        } else {
            /* EDF核心：选择绝对截止时间更早的 */
            if (pTaskB->AbsoluteDeadline < pSelected->AbsoluteDeadline) {
                pSelected = pTaskB;
            }
        }
    }

    /* 如果没有活跃任务，调度空闲（在嵌入式中可进入低功耗模式） */
    if (pSelected == NULL) {
        return;
    }

    /* ---- 第3步：执行调度决策 ---- */
    toPrio = pSelected->OSTCBPrio;

    /* 获取当前运行任务的优先级 */
    if (OSTCBCur != NULL) {
        fromPrio = OSTCBCur->OSTCBPrio;
    } else {
        fromPrio = toPrio;
    }

    /* 记录调度日志 */
    if (SchedLogIdx < LOG_SIZE) {
        SchedLog[SchedLogIdx].time     = currentTick;
        SchedLog[SchedLogIdx].fromTask = fromPrio;
        SchedLog[SchedLogIdx].toTask   = toPrio;
        SchedLog[SchedLogIdx].reason   = (fromPrio != toPrio) ? 1 : 0;
        SchedLogIdx++;
    }

    /* 如果需要切换任务，调用OS任务切换 */
    if (fromPrio != toPrio) {
        /* 设置就绪任务 */
        OSTCBPrioTbl[toPrio]->OSTCBStat = OS_STAT_RDY;
        /* 触发任务调度 */
        OSSched();
    }
}

/* ======================================================================
 *  时间片中断服务（Tick Hook）
 *  功能：在每个系统时钟tick时调用，驱动EDF调度
 *
 *  这就是题目要求的"单独的时间片中断，用于任务调度"
 *  在UCOS-II中，通过OSTimeTickHook实现
 * ====================================================================== */
void App_TimeTickHook(void)
{
    /* 递增系统计数器 */
    SystemTickCounter++;

    /* 减少当前活跃任务的剩余时间 */
    if (OSTCBCur != NULL) {
        RT_TCB *pCurrent = (RT_TCB *)OSTCBCur;

        /* 检查是否是我们的实时任务 */
        if (pCurrent->TaskID == 1 || pCurrent->TaskID == 2) {
            if (pCurrent->RemainingTime > 0) {
                pCurrent->RemainingTime--;
                pCurrent->ExecCount++;
            }

            /* 检查任务是否完成本周期的计算 */
            if (pCurrent->RemainingTime <= 0) {
                pCurrent->IsActive = FALSE;
                /* 任务完成当前周期的工作 */
                DisplayOutput(pCurrent->TaskID);
            }
        }
    }

    /* 检查截止时间是否错过 */
    if (TCB_TaskA.IsActive && SystemTickCounter > TCB_TaskA.AbsoluteDeadline) {
        TCB_TaskA.MissCount++;
        TCB_TaskA.IsActive = FALSE;
        /* 错过截止时间的处理（可输出告警） */
    }
    if (TCB_TaskB.IsActive && SystemTickCounter > TCB_TaskB.AbsoluteDeadline) {
        TCB_TaskB.MissCount++;
        TCB_TaskB.IsActive = FALSE;
    }

    /* 调用EDF调度算法 */
    EDF_Schedule();
}

/* ======================================================================
 *  显示输出函数
 *  功能：在屏幕上显示任务标识（题目要求A显示"A"，B显示"B"）
 *  说明：在嵌入式环境中可替换为LCD/串口/LED输出
 * ====================================================================== */
void DisplayOutput(INT8U taskID)
{
    if (taskID == 1) {
        /* 任务A完成一个周期的计算，在屏幕显示"A" */
        printf("[t=%ldms] A", SystemTickCounter);
    } else if (taskID == 2) {
        /* 任务B完成一个周期的计算，在屏幕显示"B" */
        printf("[t=%ldms] B", SystemTickCounter);
    }
}

/* ======================================================================
 *  任务A
 *  周期：2s（200 ticks @100Hz）
 *  计算时间：1s（100 ticks）
 *  功能：周期性在屏幕上显示"A"
 * ====================================================================== */
void TaskA(void *pdata)
{
    pdata = pdata;  /* 避免编译警告 */

    while (1) {
        /* 任务A的工作：模拟计算过程 */
        /* 在实际嵌入式系统中，这里执行具体的计算任务 */

        /*
         * 注意：实际的周期控制由EDF调度器管理
         * 任务不需要自己OSTimeDly，而是由TCB中的
         * RemainingTime和调度器控制执行
         */

        /* 模拟计算：消耗计算时间 */
        /* 在真实系统中，这里执行实际运算 */

        /* 等待调度器的下一个周期信号 */
        OSTimeDly(1);  /* 让出CPU，由调度器控制何时恢复 */
    }
}

/* ======================================================================
 *  任务B
 *  周期：5s（500 ticks @100Hz）
 *  计算时间：2.5s（250 ticks）
 *  功能：周期性在屏幕上显示"B"
 * ====================================================================== */
void TaskB(void *pdata)
{
    pdata = pdata;

    while (1) {
        /* 任务B的工作：模拟计算过程 */

        OSTimeDly(1);  /* 让出CPU，由调度器控制何时恢复 */
    }
}

/* ======================================================================
 *  时间片中断服务任务
 *  功能：创建独立任务来处理时间片中断调度
 *  说明：题目要求"写一个单独的时间片中断，用于任务调度"
 *        此任务模拟硬件定时器中断，周期性触发EDF调度
 * ====================================================================== */
void TickServiceTask(void *pdata)
{
    pdata = pdata;

    while (1) {
        /* 模拟硬件定时器中断 - 每10ms触发一次调度 */
        /* 在真实系统中，这由硬件定时器的中断服务程序完成 */
        App_TimeTickHook();

        OSTimeDly(1);  /* 1 tick = 10ms @100Hz OS_TICKS_PER_SEC */
    }
}

/* ======================================================================
 *  打印TCB信息（用于课程设计报告）
 * ====================================================================== */
void PrintTCBInfo(void)
{
    printf("\n========== TCB (Task Control Block) ==========\n\n");

    printf("Task A TCB:\n");
    printf("  TaskID:          %d\n", TCB_TaskA.TaskID);
    printf("  TaskName:        %s\n", TCB_TaskA.TaskName);
    printf("  Priority:        %d\n", TCB_TaskA.OSTCBPrio);
    printf("  Period:          %ld ticks (%.1fs)\n",
           (long)TCB_TaskA.Period,
           (double)TCB_TaskA.Period / (OS_TICKS_PER_SEC));
    printf("  ComputeTime:     %ld ticks (%.1fs)\n",
           (long)TCB_TaskA.ComputeTime,
           (double)TCB_TaskA.ComputeTime / (OS_TICKS_PER_SEC));
    printf("  Deadline:        %ld ticks (%.1fs)\n",
           (long)TCB_TaskA.Deadline,
           (double)TCB_TaskA.Deadline / (OS_TICKS_PER_SEC));
    printf("  StackSize:       %d\n", TCB_TaskA.OSTCBStkSize);
    printf("  MissCount:       %ld\n", (long)TCB_TaskA.MissCount);

    printf("\nTask B TCB:\n");
    printf("  TaskID:          %d\n", TCB_TaskB.TaskID);
    printf("  TaskName:        %s\n", TCB_TaskB.TaskName);
    printf("  Priority:        %d\n", TCB_TaskB.OSTCBPrio);
    printf("  Period:          %ld ticks (%.1fs)\n",
           (long)TCB_TaskB.Period,
           (double)TCB_TaskB.Period / (OS_TICKS_PER_SEC));
    printf("  ComputeTime:     %ld ticks (%.1fs)\n",
           (long)TCB_TaskB.ComputeTime,
           (double)TCB_TaskB.ComputeTime / (OS_TICKS_PER_SEC));
    printf("  Deadline:        %ld ticks (%.1fs)\n",
           (long)TCB_TaskB.Deadline,
           (double)TCB_TaskB.Deadline / (OS_TICKS_PER_SEC));
    printf("  StackSize:       %d\n", TCB_TaskB.OSTCBStkSize);
    printf("  MissCount:       %ld\n", (long)TCB_TaskB.MissCount);

    printf("\n==============================================\n\n");
}

/* ======================================================================
 *  打印调度日志（用于课程设计报告分析）
 * ====================================================================== */
void PrintScheduleLog(void)
{
    INT32U i;

    printf("\n========== Schedule Log ==========\n\n");
    printf("%-10s %-12s %-12s %-10s\n",
           "Time(tick)", "FromTask", "ToTask", "Reason");
    printf("----------------------------------------------\n");

    for (i = 0; i < SchedLogIdx && i < LOG_SIZE; i++) {
        const char *fromName, *toName, *reason;

        switch (SchedLog[i].fromTask) {
            case TASK_A_PRIO: fromName = "TaskA"; break;
            case TASK_B_PRIO: fromName = "TaskB"; break;
            default:          fromName = "Idle";  break;
        }
        switch (SchedLog[i].toTask) {
            case TASK_A_PRIO: toName = "TaskA"; break;
            case TASK_B_PRIO: toName = "TaskB"; break;
            default:          toName = "Idle";  break;
        }
        switch (SchedLog[i].reason) {
            case 0: reason = "完成";  break;
            case 1: reason = "抢占";  break;
            case 2: reason = "新到达"; break;
            default: reason = "未知"; break;
        }

        printf("%-10ld %-12s %-12s %-10s\n",
               (long)SchedLog[i].time, fromName, toName, reason);
    }

    printf("\n总调度次数: %ld\n", (long)SchedLogIdx);
    printf("==================================\n\n");
}

/* ======================================================================
 *  主函数
 * ====================================================================== */
int main(void)
{
    /* 初始化UCOS-II */
    OSInit();

    /* 初始化任务控制块(TCB)结构 */
    /*
     * 这里展示了题目要求的"AB两个任务的PCB(TCB)结构"
     * RT_TCB结构在app_cfg.h中定义，包含了UCOS-II原生TCB字段
     * 和扩展的实时调度字段（周期、截止时间、计算时间等）
     */
    RT_TCB_Init(&TCB_TaskA, TASK_A_PRIO, 1,
                TASK_A_PERIOD, TASK_A_COMPUTE, TASK_A_DEADLINE, "TA");

    RT_TCB_Init(&TCB_TaskB, TASK_B_PRIO, 2,
                TASK_B_PERIOD, TASK_B_COMPUTE, TASK_B_DEADLINE, "TB");

    /* 打印TCB信息 */
    PrintTCBInfo();

    /* 创建时间片中断服务任务（题目要求1） */
    OSTaskCreate(TickServiceTask,
                 (void *)0,
                 &TickService_Stk[TASK_STK_SIZE - 1],
                 TASK_TICK_SERVICE_PRIO);

    /* 创建任务A（题目要求3：显示"A"） */
    OSTaskCreate(TaskA,
                 (void *)0,
                 &TaskA_Stk[TASK_STK_SIZE - 1],
                 TASK_A_PRIO);

    /* 创建任务B（题目要求3：显示"B"） */
    OSTaskCreate(TaskB,
                 (void *)0,
                 &TaskB_Stk[TASK_STK_SIZE - 1],
                 TASK_B_PRIO);

    /* 启动多任务调度 */
    OSStart();

    return 0;
}
