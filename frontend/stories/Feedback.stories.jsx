import React, {useState} from 'react';
import {expect, userEvent, waitFor, within} from 'storybook/test';
import FeedbackHost, {confirmAction, toast} from '../src/feedback';
import AccessibilityManager from '../src/AccessibilityManager';
import ListEditor from '../src/ListEditor';
import useAppViewport from '../src/use-app-viewport';

export default {title: 'FamilyOS/Feedback'};
export const Confirmation = {
  render: function Confirmation() {
    const [result, setResult] = useState('');
    return <><AccessibilityManager/><FeedbackHost/><button className="destructive" onClick={async () => setResult(await confirmAction({title: 'Eintrag entfernen?', message: 'Die gemeinsame Liste bleibt erhalten.', danger: true}) ? 'Entfernt' : 'Abgebrochen')}>Eintrag entfernen</button><p role="status">{result}</p></>;
  },
  play: async ({canvasElement}) => {
    const canvas = within(canvasElement), body = within(canvasElement.ownerDocument.body);
    const trigger = canvas.getByRole('button', {name: 'Eintrag entfernen'});
    await userEvent.click(trigger);
    const dialog = await body.findByRole('alertdialog');
    await userEvent.click(within(dialog).getByRole('button', {name: 'Abbrechen'}));
    await waitFor(() => expect(trigger).toHaveFocus());
    await expect(canvas.getByRole('status')).toHaveTextContent('Abgebrochen');
  },
};
export const Toast = {
  render: function Toast() {
    const [result, setResult] = useState('');
    return <><FeedbackHost/><button className="primary" onClick={() => toast('Liste archiviert.', {type: 'success', duration: 30000, actionLabel: 'Rückgängig', onAction: () => setResult('Wiederhergestellt')})}>Archivieren</button><p role="status">{result}</p></>;
  },
  play: async ({canvasElement}) => {
    const canvas = within(canvasElement), body = within(canvasElement.ownerDocument.body);
    await userEvent.click(canvas.getByRole('button', {name: 'Archivieren'}));
    await userEvent.click(await body.findByRole('button', {name: 'Rückgängig'}));
    await expect(canvas.getByRole('status')).toHaveTextContent('Wiederhergestellt');
    await userEvent.click(canvas.getByRole('button', {name: 'Archivieren'}));
    await userEvent.click(await body.findByRole('button', {name: 'Meldung schließen'}));
    await expect(body.queryByText('Liste archiviert.')).not.toBeInTheDocument();
  },
};
export const QuickCreate = {
  render: function QuickCreate() {
    useAppViewport();
    const [open, setOpen] = useState(false);
    return <><AccessibilityManager/><FeedbackHost/><button className="primary" onClick={() => setOpen(true)}>Aufgabenliste erstellen</button>{open && <ListEditor type="task" family={{id: 9000, memberships: [{user: 9001, role: 'owner'}]}} onClose={() => setOpen(false)} onSaved={() => setOpen(false)}/>}</>;
  },
  play: async ({canvasElement}) => {
    const canvas = within(canvasElement), body = within(canvasElement.ownerDocument.body);
    const trigger = canvas.getByRole('button', {name: 'Aufgabenliste erstellen'});
    await userEvent.click(trigger);
    const dialog = within(await body.findByRole('dialog'));
    await userEvent.type(dialog.getByRole('textbox', {name: /Name/}), 'Sommerferienplanung Beispiel');
    await expect(dialog.getByRole('button', {name: 'Speichern'})).toBeEnabled();
    await userEvent.click(dialog.getByRole('button', {name: 'Abbrechen'}));
    await waitFor(() => expect(trigger).toHaveFocus());
  },
};
