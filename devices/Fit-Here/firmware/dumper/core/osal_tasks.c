// OSAL task table of the dumper: link layer, HCI (both in ROM) and the dumper. No BLE host.
// Adapted from lib/core/osal_tasks.c of e-labInnovations/FitPro-LP715-PHY6222.
#include "OSAL.h"
#include "OSAL_Tasks.h"
#include "osal_cbtimer.h"
#include "ll.h"
#include "hci_tl.h"

extern void dumper_init(uint8 task_id);
extern uint16 dumper_process_event(uint8 task_id, uint16 events);

const pTaskEventHandlerFn tasksArr[] = {
    LL_ProcessEvent,
    HCI_ProcessEvent,
#if defined(OSAL_CBTIMER_NUM_TASKS)
    OSAL_CBTIMER_PROCESS_EVENT(osal_CbTimerProcessEvent),
#endif
    dumper_process_event,
};

const uint8 tasksCnt = sizeof(tasksArr) / sizeof(tasksArr[0]);
uint16 *tasksEvents;

void osalInitTasks(void) {
    uint8 taskID = 0;

    tasksEvents = (uint16 *)osal_mem_alloc(sizeof(uint16) * tasksCnt);
    osal_memset(tasksEvents, 0, sizeof(uint16) * tasksCnt);

    LL_Init(taskID++);
    HCI_Init(taskID++);
#if defined(OSAL_CBTIMER_NUM_TASKS)
    osal_CbTimerInit(taskID);
    taskID += OSAL_CBTIMER_NUM_TASKS;
#endif
    dumper_init(taskID++);
}
