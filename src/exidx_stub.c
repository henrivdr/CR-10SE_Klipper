/* Weak stub definitions for ARM .exidx table symbols.
   These satisfy libgcc unwind references when no .ARM.exidx is present.
*/

__attribute__((weak)) void *__exidx_start = 0;
__attribute__((weak)) void *__exidx_end = 0;
