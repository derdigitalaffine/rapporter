import React, {useState} from 'react';
import {expect, userEvent, within, waitFor} from 'storybook/test';
import FamilyCombobox from '../src/ui/FamilyCombobox';
import FeedbackHost, {confirmAction, toast} from '../src/feedback';
import AccessibilityManager from '../src/AccessibilityManager';

export default {title: 'FamilyOS/Interactions'};
const items = [{id: 9001, name: 'Alexandra Beispiel mit einem sehr langen Doppelnamen'}, {id: 9002, name: 'Robin Beispiel'}];
function Picker({multiple = true, ...props}) {
  const [selectedIds, onChange] = useState([]);
  return <FamilyCombobox label="Teilnehmende" items={items} selectedIds={selectedIds} onChange={onChange} multiple={multiple} {...props}/>;
}
export const MultiPicker = {
  render: () => <Picker/>,
  play: async ({canvasElement}) => {
    const canvas = within(canvasElement);
    const input = canvas.getByRole('combobox', {name: 'Teilnehmende'});
    await userEvent.type(input, 'Robin');
    await userEvent.keyboard('{ArrowDown}{Enter}');
    await userEvent.click(await canvas.findByRole('button', {name: 'Robin Beispiel Entfernen'}));
    await expect(canvas.queryByRole('list', {name: 'Teilnehmende: Auswahl'})).not.toBeInTheDocument();
  },
};
export const SinglePicker = {render: () => <Picker multiple={false}/>};
export const AsyncLoading = {render: () => <Picker loading items={[]}/>};
export const AsyncEmpty = {render: () => <Picker items={[]}/>};
export const AsyncError = {render: () => <Picker items={[]} error="Personen konnten nicht geladen werden."/>};
export const PickerDisabled = {render: () => <Picker disabled/>};
export const ConfirmQueue = {
  render: function ConfirmQueue() {
    const [result, setResult] = useState('');
    return <><AccessibilityManager/><FeedbackHost/><button className="primary" onClick={async () => {const first = confirmAction({title: 'Erste Anfrage'}); const second = confirmAction({title: 'Zweite Anfrage'}); setResult(`${await first}/${await second}`);}}>Zwei Anfragen</button><p role="status">{result}</p></>;
  },
  play: async ({canvasElement}) => {
    const canvas = within(canvasElement), body = within(canvasElement.ownerDocument.body);
    const trigger = canvas.getByRole('button');
    await userEvent.click(trigger);
    await userEvent.click(within(await body.findByRole('alertdialog', {name: 'Erste Anfrage'})).getByRole('button', {name: 'Bestätigen'}));
    await body.findByRole('alertdialog', {name: 'Zweite Anfrage'});
    await userEvent.keyboard('{Escape}');
    await waitFor(() => expect(trigger).toHaveFocus());
    await expect(canvas.getByRole('status')).toHaveTextContent('true/false');
  },
};
export const ToastDeduplication = {
  render: () => <><FeedbackHost/><button className="primary" onClick={() => {for (let i = 0; i < 5; i++) toast('Verbindung wiederhergestellt.', {type: 'success'});}}>Verbindungsstatus</button></>,
  play: async ({canvasElement}) => {
    await userEvent.click(within(canvasElement).getByRole('button'));
    const body = within(canvasElement.ownerDocument.body);
    await expect(body.getAllByText('Verbindung wiederhergestellt.')).toHaveLength(1);
    await userEvent.click(body.getByRole('button', {name: 'Meldung schließen'}));
  },
};
