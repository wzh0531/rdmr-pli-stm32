                PRESERVE8
                THUMB

Stack_Size      EQU     0x00001000
                AREA    STACK, NOINIT, READWRITE, ALIGN=3
Stack_Mem       SPACE   Stack_Size
__initial_sp

                AREA    RESET, DATA, READONLY
                EXPORT  __Vectors
                EXPORT  __Vectors_End
                EXPORT  __Vectors_Size

__Vectors       DCD     __initial_sp
                DCD     Reset_Handler
                DCD     NMI_Handler
                DCD     HardFault_Handler
                DCD     MemManage_Handler
                DCD     BusFault_Handler
                DCD     UsageFault_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     SVC_Handler
                DCD     DebugMon_Handler
                DCD     Default_Handler
                DCD     PendSV_Handler
                DCD     SysTick_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
                DCD     Default_Handler
__Vectors_End
__Vectors_Size  EQU     __Vectors_End - __Vectors

                AREA    |.text|, CODE, READONLY

Reset_Handler   PROC
                EXPORT  Reset_Handler
                IMPORT  SystemInit
                IMPORT  main
                ; Proteus cannot reliably execute the ARMCC scatter-loading
                ; runtime for this model, so initialise the used RAM directly.
                LDR     R0, =0x20000000
                LDR     R1, =Stack_Mem
                MOVS    R2, #0
Reset_ClearLoop
                CMP     R0, R1
                BCS     Reset_ClearDone
                STR     R2, [R0], #4
                B       Reset_ClearLoop
Reset_ClearDone
                BL      SystemInit
                BL      main
                B       .
                ENDP

NMI_Handler     PROC
                EXPORT  NMI_Handler
                B       .
                ENDP

HardFault_Handler PROC
                EXPORT  HardFault_Handler
                B       .
                ENDP

MemManage_Handler PROC
                EXPORT  MemManage_Handler
                B       .
                ENDP

BusFault_Handler PROC
                EXPORT  BusFault_Handler
                B       .
                ENDP

UsageFault_Handler PROC
                EXPORT  UsageFault_Handler
                B       .
                ENDP

SVC_Handler     PROC
                EXPORT  SVC_Handler
                B       .
                ENDP

DebugMon_Handler PROC
                EXPORT  DebugMon_Handler
                B       .
                ENDP

PendSV_Handler  PROC
                EXPORT  PendSV_Handler
                B       .
                ENDP

SysTick_Handler PROC
                EXPORT  SysTick_Handler
                B       .
                ENDP

Default_Handler PROC
                EXPORT  Default_Handler
                B       .
                ENDP

                ALIGN
                END
