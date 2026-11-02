import {useId, useRef, type ReactNode} from 'react';

/** A keyboard- and touch-accessible home for secondary explanations. */
export default function InfoPopover({title, children}: {title: string; children: ReactNode}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const heading = useId();
  return <span className="info-popover">
    <button className="info-button" type="button" aria-label={`About ${title}`} aria-haspopup="dialog" onClick={() => dialog.current?.showModal()}>i</button>
    <dialog className="info-dialog" ref={dialog} aria-labelledby={heading} onClick={event => {
      if(event.target !== event.currentTarget) return;
      const box = event.currentTarget.getBoundingClientRect();
      if(event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) event.currentTarget.close();
    }}>
      <div className="info-dialog-heading"><h2 id={heading}>{title}</h2><button type="button" aria-label="Close information" onClick={() => dialog.current?.close()}>Close</button></div>
      <div className="info-dialog-body">{children}</div>
    </dialog>
  </span>;
}
