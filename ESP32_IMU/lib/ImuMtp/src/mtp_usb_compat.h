#pragma once
#include "soc/usb_reg.h"
#include "soc/usb_struct.h"
// TinyUSB 0.16 has no RX_PENDING state; rearming already consumes its OUT buffer.
static inline void usbd_edpt_rx_consume(uint8_t port, uint8_t ep) { (void)port; (void)ep; }
// ESP32-S3 DCD 0.16 stalls by disabling the endpoint and flushing its FIFO.
// Clearing the halt resets DATA0 and busy; release the old claim as well.
static inline void usbd_edpt_abort(uint8_t port, uint8_t ep) {
    usbd_edpt_stall(port, ep);
    usbd_edpt_clear_stall(port, ep);
    usbd_edpt_release(port, ep);
}
// Host Cancel does not reset its bulk data toggle. The ordinary clear-halt
// helper does, so retain DWC2 DOEPCTL.DPID (bit 16) while retiring an OUT read.
static inline void usbd_edpt_cancel_out(uint8_t port, uint8_t ep) {
    volatile uint32_t* reg = &USB0.out_ep_reg[tu_edpt_number(ep)].doepctl;
    usbd_edpt_stall(port, ep);
    const bool data1 = (*reg & BIT(16)) != 0;
    usbd_edpt_clear_stall(port, ep);
    *reg |= data1 ? USB_DO_SETD1PID1 : USB_DO_SETD0PID1;
    usbd_edpt_release(port, ep);
}
// 0.16's defer function always enqueues at the tail, including on the USB task.
static inline bool usbd_defer_func_after_queue(osal_task_func_t fn, void *arg) {
    usbd_defer_func(fn, arg, false);
    return true;
}
#define usbd_edpt_xfer(port, ep, buffer, length, in_isr) usbd_edpt_xfer(port, ep, buffer, length)
