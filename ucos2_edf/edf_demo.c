/*
 * ========================================================================
 *  课程设计2026 - 模拟PC环境的EDF调度演示程序
 *  可在Windows/Linux下编译运行，模拟UCOS-II的EDF调度过程
 * ========================================================================
 *
 *  编译方式（GCC）：
 *    gcc -o edf_demo edf_demo.c -lm
 *
 *  此程序脱离UCOS-II依赖，在PC上模拟EDF调度算法的行为，
 *  用于验证调度逻辑的正确性和生成调度日志/时间图。
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* ======================================================================
 *  参数定义（与教材P94图3-10对应）
 * ====================================================================== */

/* 缩放因子：将教材中的ms级参数放大到便于观察的级别 */
#define SCALE               100

/* 任务参数（原始值，单位ms） */
#define TASK_A_PERIOD       20      /* A的周期 */
#define TASK_A_COMPUTE      10      /* A的计算时间 */
#define TASK_A_DEADLINE     20      /* A的截止时间 */

#define TASK_B_PERIOD       50      /* B的周期 */
#define TASK_B_COMPUTE      25      /* B的计算时间 */
#define TASK_B_DEADLINE     50      /* B的截止时间 */

/* 模拟总时长（tick数） */
#define SIM_DURATION        200     /* 模拟200个时间单位 */
#define TICK_MS             1       /* 每个tick代表1ms */

/* ======================================================================
 *  TCB（任务控制块）结构
 * ====================================================================== */
typedef struct {
    char  name[4];          /* 任务名称 */
    int   period;           /* 周期（ms） */
    int   computeTime;      /* 计算时间（ms） */
    int   deadline;         /* 截止时间（ms） */

    /* 运行时状态 */
    int   remainingTime;    /* 剩余计算时间 */
    int   nextArrival;      /* 下一次到达时间 */
    int   absDeadline;      /* 当前周期的绝对截止时间 */
    int   isActive;         /* 是否在当前周期内活跃 */

    /* 统计 */
    int   execCount;        /* 执行总tick数 */
    int   completeCount;    /* 完成的周期数 */
    int   missCount;        /* 错过截止时间次数 */
} PCB_TCB;

/* ======================================================================
 *  调度日志
 * ====================================================================== */
typedef struct {
    int  time;
    int  fromTask;     /* 0=空闲, 1=A, 2=B */
    int  toTask;
    int  reason;       /* 0=完成, 1=抢占 */
} LogEntry;

LogEntry logs[512];
int logCount = 0;

/* ======================================================================
 *  记录调度事件
 * ====================================================================== */
void addLog(int time, int from, int to, int reason)
{
    if (logCount < 512) {
        logs[logCount].time = time;
        logs[logCount].fromTask = from;
        logs[logCount].toTask = to;
        logs[logCount].reason = reason;
        logCount++;
    }
}

/* ======================================================================
 *  打印TCB结构信息
 * ====================================================================== */
void printTCB(PCB_TCB *tcb)
{
    printf("  %-12s | 周期: %3dms | 计算时间: %3dms | 截止时间: %3dms\n",
           tcb->name, tcb->period, tcb->computeTime, tcb->deadline);
}

/* ======================================================================
 *  EDF调度算法 - 核心
 *  返回应运行的任务编号 (1=A, 2=B, 0=空闲)
 * ====================================================================== */
int edfSelect(PCB_TCB *taskA, PCB_TCB *taskB)
{
    int selected = 0;
    int minDeadline = 0x7FFFFFFF;

    if (taskA->isActive && taskA->remainingTime > 0) {
        if (taskA->absDeadline < minDeadline) {
            minDeadline = taskA->absDeadline;
            selected = 1;
        }
    }

    if (taskB->isActive && taskB->remainingTime > 0) {
        if (taskB->absDeadline < minDeadline) {
            minDeadline = taskB->absDeadline;
            selected = 2;
        }
    }

    return selected;
}

/* ======================================================================
 *  生成时间图（类似教材图3-10的甘特图）
 * ====================================================================== */
void printGanttChart(int *schedule, int duration)
{
    int i;
    printf("\n时间图（Gantt Chart）：\n");
    printf("时间轴: ");
    for (i = 0; i <= duration; i += 10) {
        printf("%-10d", i);
    }
    printf("\n        ");
    for (i = 0; i <= duration; i += 10) {
        printf(" |");
    }
    printf("\n调度:   ");
    for (i = 0; i < duration; i++) {
        switch (schedule[i]) {
            case 1:  printf("A"); break;
            case 2:  printf("B"); break;
            default: printf("."); break;
        }
    }
    printf("\n\n");
}

/* ======================================================================
 *  主模拟函数
 * ====================================================================== */
int main(void)
{
    PCB_TCB taskA, taskB;
    int currentTick;
    int currentTask = 0;  /* 当前运行的任务 */
    int schedule[SIM_DURATION];  /* 记录每个tick的调度结果 */

    printf("================================================================\n");
    printf("  课程设计：UCOS-II周期实时任务抢占式调度 - EDF算法演示\n");
    printf("  教材P94 - 图3-10 EDF算法用于抢占式调度方式之例\n");
    printf("================================================================\n\n");

    /* ---- 初始化TCB ---- */
    memset(&taskA, 0, sizeof(PCB_TCB));
    memset(&taskB, 0, sizeof(PCB_TCB));

    strcpy(taskA.name, "TaskA");
    taskA.period      = TASK_A_PERIOD;
    taskA.computeTime = TASK_A_COMPUTE;
    taskA.deadline    = TASK_A_DEADLINE;
    taskA.remainingTime = 0;
    taskA.nextArrival = 0;
    taskA.absDeadline = 0;
    taskA.isActive    = 0;

    strcpy(taskB.name, "TaskB");
    taskB.period      = TASK_B_PERIOD;
    taskB.computeTime = TASK_B_COMPUTE;
    taskB.deadline    = TASK_B_DEADLINE;
    taskB.remainingTime = 0;
    taskB.nextArrival = 0;
    taskB.absDeadline = 0;
    taskB.isActive    = 0;

    /* ---- 打印TCB结构 ---- */
    printf("【1】任务控制块(TCB/PCB)结构：\n\n");
    printf("  ┌─────────────┬──────────┬──────────┬──────────┐\n");
    printf("  │   字段名     │  TaskA   │  TaskB   │   说明   │\n");
    printf("  ├─────────────┼──────────┼──────────┼──────────┤\n");
    printf("  │ name        │ %-8s │ %-8s │ 任务名   │\n", taskA.name, taskB.name);
    printf("  │ period      │ %4dms   │ %4dms   │ 周期     │\n", taskA.period, taskB.period);
    printf("  │ computeTime │ %4dms   │ %4dms   │ 计算时间 │\n", taskA.computeTime, taskB.computeTime);
    printf("  │ deadline    │ %4dms   │ %4dms   │ 截止时间 │\n", taskA.deadline, taskB.deadline);
    printf("  │ priority    │ %4d     │ %4d     │ 优先级   │\n", 5, 6);
    printf("  │ stackSize   │ %4d     │ %4d     │ 栈大小   │\n", 256, 256);
    printf("  └─────────────┴──────────┴──────────┴──────────┘\n\n");

    printTCB(&taskA);
    printTCB(&taskB);

    /* ---- 模拟EDF调度 ---- */
    printf("\n【2】EDF抢占式调度模拟：\n");
    printf("  调度规则：选择绝对截止时间最早的任务运行\n");
    printf("  抢占条件：新任务到达时，若其截止时间 < 当前任务截止时间\n\n");

    memset(schedule, 0, sizeof(schedule));
    logCount = 0;

    for (currentTick = 0; currentTick < SIM_DURATION; currentTick++) {

        /* 检查任务A到达 */
        if (currentTick >= taskA.nextArrival) {
            if (!taskA.isActive || taskA.remainingTime <= 0) {
                taskA.isActive = 1;
                taskA.remainingTime = taskA.computeTime;
                taskA.absDeadline = currentTick + taskA.deadline;
                taskA.nextArrival = currentTick + taskA.period;
            }
        }

        /* 检查任务B到达 */
        if (currentTick >= taskB.nextArrival) {
            if (!taskB.isActive || taskB.remainingTime <= 0) {
                taskB.isActive = 1;
                taskB.remainingTime = taskB.computeTime;
                taskB.absDeadline = currentTick + taskB.deadline;
                taskB.nextArrival = currentTick + taskB.period;
            }
        }

        /* EDF选择 */
        int selected = edfSelect(&taskA, &taskB);

        /* 记录调度 */
        schedule[currentTick] = selected;

        /* 检查是否发生抢占 */
        if (selected != currentTask && currentTask != 0) {
            addLog(currentTick, currentTask, selected, 1);
        }

        currentTask = selected;

        /* 执行1个tick */
        if (selected == 1) {
            taskA.remainingTime--;
            taskA.execCount++;
            if (taskA.remainingTime <= 0) {
                taskA.isActive = 0;
                taskA.completeCount++;
                printf("  t=%3dms: 任务A显示\"A\" (周期%d完成)\n",
                       currentTick, taskA.completeCount);
            }
        } else if (selected == 2) {
            taskB.remainingTime--;
            taskB.execCount++;
            if (taskB.remainingTime <= 0) {
                taskB.isActive = 0;
                taskB.completeCount++;
                printf("  t=%3dms: 任务B显示\"B\" (周期%d完成)\n",
                       currentTick, taskB.completeCount);
            }
        }
    }

    /* ---- 打印调度日志 ---- */
    printf("\n【3】调度事件日志：\n\n");
    printf("  %-10s  %-10s  %-10s  %-10s\n", "时间(tick)", "离开任务", "运行任务", "原因");
    printf("  -----------------------------------------------\n");

    {
        int i;
        for (i = 0; i < logCount; i++) {
            const char *from = (logs[i].fromTask == 1) ? "TaskA" :
                               (logs[i].fromTask == 2) ? "TaskB" : "Idle";
            const char *to   = (logs[i].toTask == 1) ? "TaskA" :
                               (logs[i].toTask == 2) ? "TaskB" : "Idle";
            const char *reason = (logs[i].reason == 1) ? "抢占" : "完成";
            printf("  t=%-7d  %-10s  %-10s  %s\n",
                   logs[i].time, from, to, reason);
        }
    }

    /* ---- 打印时间图 ---- */
    printGanttChart(schedule, SIM_DURATION);

    /* ---- 打印统计 ---- */
    printf("【4】运行统计：\n\n");
    printf("  任务A: 完成周期数 = %d, 执行tick数 = %d, 错过截止 = %d\n",
           taskA.completeCount, taskA.execCount, taskA.missCount);
    printf("  任务B: 完成周期数 = %d, 执行tick数 = %d, 错过截止 = %d\n",
           taskB.completeCount, taskB.execCount, taskB.missCount);

    printf("\n  CPU利用率 = (A计算时间/A周期 + B计算时间/B周期) * 100%%\n");
    printf("            = (%d/%d + %d/%d) * 100%% = %.1f%%\n",
           TASK_A_COMPUTE, TASK_A_PERIOD,
           TASK_B_COMPUTE, TASK_B_PERIOD,
           ((double)TASK_A_COMPUTE / TASK_A_PERIOD +
            (double)TASK_B_COMPUTE / TASK_B_PERIOD) * 100.0);

    printf("\n================================================================\n");
    printf("  模拟完成\n");
    printf("================================================================\n\n");

    return 0;
}
