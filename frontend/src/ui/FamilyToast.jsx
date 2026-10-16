import {Toast} from '@base-ui/react/toast';
import {Icon} from '../icons';
import './interaction-primitives.css';

const manager = Toast.createToastManager();
const active = new Map();
let nextToast = 1;
export function familyToast(message, {type = 'info', actionLabel = '', onAction = null, duration = 6000} = {}) {
  if (message === 'unauthorized') return null;
  const key = JSON.stringify([message, type, actionLabel]);
  const id = active.get(key) || `family-toast-${nextToast++}`;
  active.set(key, id);
  manager.add({id, title: message, type, timeout: duration, priority: type === 'error' ? 'high' : 'low', data: {actionLabel, onAction}, onClose: () => {if (active.get(key) === id) active.delete(key);}});
  return id;
}
function ToastList() {
  const {toasts} = Toast.useToastManager();
  return <Toast.Portal><Toast.Viewport className="toast-region" aria-label="Meldungen">
    {toasts.map(item => <Toast.Root key={item.id} toast={item} className={`toast toast-${item.type}`}>
      <span className="toast-icon" aria-hidden="true"><Icon name={item.type === 'success' ? 'check' : ['error', 'warning'].includes(item.type) ? 'warning' : 'info'}/></span>
      <Toast.Title className="toast-message"/>
      {item.data?.actionLabel && <Toast.Action className="toast-action" onClick={() => {manager.close(item.id); item.data.onAction?.();}}>{item.data.actionLabel}</Toast.Action>}
      <Toast.Close className="toast-close" aria-label="Meldung schließen"><Icon name="close"/></Toast.Close>
    </Toast.Root>)}
  </Toast.Viewport></Toast.Portal>;
}
export default function FamilyToastHost() {
  return <Toast.Provider toastManager={manager} limit={3} timeout={6000}><ToastList/></Toast.Provider>;
}
