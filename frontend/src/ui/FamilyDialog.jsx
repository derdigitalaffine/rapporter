import {useRef} from 'react';
import {AlertDialog} from '@base-ui/react/alert-dialog';
import {Icon} from '../icons';
import useOverlayOwnership from './useOverlayOwnership';
import './interaction-primitives.css';

export default function FamilyDialog({title, message, confirmLabel, cancelLabel, danger, onAnswer, returnFocus}) {
  const restoreFocus=useOverlayOwnership();
  const cancel = useRef(null);
  return <AlertDialog.Root open onOpenChange={open => {if (!open) onAnswer(false);}}>
    <AlertDialog.Portal>
      <AlertDialog.Backdrop className="sheet-backdrop confirm-backdrop"/>
      <AlertDialog.Viewport className="family-dialog-viewport confirm-backdrop" data-app-modal-root>
        <AlertDialog.Popup className="confirm-dialog" aria-modal="true" data-family-overlay-owner="base-ui" initialFocus={cancel} finalFocus={() => restoreFocus(returnFocus)}>
          <div className={`confirm-icon ${danger ? 'danger' : ''}`}><Icon name={danger ? 'warning' : 'info'}/></div>
          <AlertDialog.Title render={<h2/>}>{title}</AlertDialog.Title>
          {message && <AlertDialog.Description render={<p/>}>{message}</AlertDialog.Description>}
          <div className="confirm-actions">
            <AlertDialog.Close ref={cancel} className="secondary" onClick={() => onAnswer(false)}>{cancelLabel}</AlertDialog.Close>
            <button className={danger ? 'destructive' : 'primary compact'} onClick={() => onAnswer(true)}>{confirmLabel}</button>
          </div>
        </AlertDialog.Popup>
      </AlertDialog.Viewport>
    </AlertDialog.Portal>
  </AlertDialog.Root>;
}
