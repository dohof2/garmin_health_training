/** Dismiss native modal backdrops, preserving clicks and drags inside the panel. */
export function installLightDismiss() {
  let pressed: HTMLDialogElement | null = null;
  const outside = (event: MouseEvent | PointerEvent): HTMLDialogElement | null => {
    const target = event.target;
    if (!(target instanceof HTMLDialogElement) || !target.open) return null;
    const box = target.getBoundingClientRect();
    return event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom ? target : null;
  };
  document.addEventListener('pointerdown', event => { pressed = outside(event); }, true);
  document.addEventListener('click', event => {
    const dialog = outside(event);
    if (dialog && dialog === pressed) dialog.close();
    pressed = null;
  }, true);
}
