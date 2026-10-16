import {useRef} from 'react';
import {Drawer} from '@base-ui/react/drawer';
import useOverlayOwnership from './useOverlayOwnership';
import './interaction-primitives.css';

export default function FamilySheet({children, labelledBy, onClose, busy = false}) {
  useOverlayOwnership();
  const returnFocus = useRef(document.activeElement);
  return <Drawer.Root open onOpenChange={(open, details) => {if (!open) {if (busy) details.cancel(); else onClose();}}} disablePointerDismissal={busy}>
    <Drawer.VirtualKeyboardProvider>
      <Drawer.Portal>
        <Drawer.Backdrop className="sheet-backdrop" data-family-overlay-owner="base-ui"/>
        <Drawer.Viewport className="sheet-backdrop family-sheet-viewport" data-family-overlay-owner="base-ui" data-app-modal-root>
          <Drawer.Popup className="quick-sheet family-sheet" aria-labelledby={labelledBy} data-family-overlay-owner="base-ui" initialFocus={type => type === 'touch' ? true : document.getElementById(labelledBy)?.closest('.quick-sheet')?.querySelector('input:not([disabled])') || true} finalFocus={() => returnFocus.current?.isConnected ? returnFocus.current : true}>
            {children}
          </Drawer.Popup>
        </Drawer.Viewport>
      </Drawer.Portal>
    </Drawer.VirtualKeyboardProvider>
  </Drawer.Root>;
}
