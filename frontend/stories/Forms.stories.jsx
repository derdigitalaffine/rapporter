import React, {useState} from 'react';
import {expect, userEvent, within} from 'storybook/test';
import {ChoiceField, EntityPicker, ErrorSummary, FormActions, FormField, FormRow, FormSection, FormShell, ProgressiveFieldGroup} from '../src/form-primitives';
import {Icon} from '../src/icons';

export default {title: 'FamilyOS/Forms'};
const people = [{id: 9001, name: 'Alexandra Beispiel mit einem sehr langen Doppelnamen'}, {id: 9002, name: 'Robin Beispiel'}];

export const Fields = {
  render: function Fields() {
    const [choice, setChoice] = useState('family');
    return <FormShell title="Reisebudget" onSubmit={event => event.preventDefault()}>
      <FormSection legend="Planung">
        <FormRow><FormField label="Bezeichnung" required><input defaultValue="Sommerferien mit der ganzen Familie"/></FormField><FormField label="Betrag" description="Euro"><input type="number" defaultValue="12345.67" step="0.01"/></FormField></FormRow>
        <ChoiceField legend="Sichtbarkeit" value={choice} onChange={setChoice} options={[{value: 'family', label: 'Familie'}, {value: 'private', label: 'Nur ich'}]}/>
        <ProgressiveFieldGroup label="Weitere Angaben"><FormField label="Notiz"><textarea defaultValue="Anreise und Unterkunft"/></FormField></ProgressiveFieldGroup>
      </FormSection>
      <FormActions><button type="button" className="secondary">Abbrechen</button><button className="primary"><Icon name="check"/> Speichern</button></FormActions>
    </FormShell>;
  },
};
export const Validation = {
  render: function Validation() {
    const [errors, setErrors] = useState([]);
    return <FormShell title="Bezeichnung bearbeiten" noValidate onSubmit={event => {event.preventDefault(); setErrors([{id: 'example-name', label: 'Bezeichnung', message: 'Bitte eine Bezeichnung eingeben.'}]);}}>
      <ErrorSummary errors={errors}/><FormField id="example-name" label="Bezeichnung" error={errors[0]?.message} required><input/></FormField><FormActions><button className="primary">Speichern</button></FormActions>
    </FormShell>;
  },
  play: async ({canvasElement}) => {
    const canvas = within(canvasElement);
    await userEvent.click(canvas.getByRole('button', {name: 'Speichern'}));
    await expect(canvas.getByRole('alert')).toHaveFocus();
    await userEvent.click(canvas.getByRole('link'));
    await expect(canvas.getByRole('textbox')).toHaveFocus();
  },
};
export const Picker = {
  render: function Picker() {
    const [selected, setSelected] = useState([]);
    return <EntityPicker label="Teilnehmende" items={people} selectedIds={selected} onChange={setSelected}/>;
  },
  play: async ({canvasElement}) => {
    const canvas = within(canvasElement);
    await userEvent.type(canvas.getByLabelText('Teilnehmende'), 'Robin');
    await userEvent.click(canvas.getByRole('button', {name: 'Robin Beispiel'}));
    await userEvent.click(canvas.getByRole('button', {name: 'Robin Beispiel Entfernen'}));
    await expect(canvas.queryByRole('list', {name: 'Teilnehmende: Auswahl'})).not.toBeInTheDocument();
  },
};
export const EmptyPicker = {render: () => <EntityPicker label="Teilnehmende" items={[]} selectedIds={[]} emptyMessage="Keine Personen gefunden"/>};
export const Disabled = {render: () => <FormShell title="Budget"><FormField label="Geplanter Betrag"><input disabled defaultValue="12345,67 EUR"/></FormField><ChoiceField legend="Sichtbarkeit" disabled value="family" options={[{value: 'family', label: 'Familie'}]}/><FormActions><button className="primary" disabled>Speichern</button></FormActions></FormShell>};
export const Loading = {render: () => <FormShell title="Budget" aria-busy="true"><p role="status">Wird geladen …</p><FormActions><button className="primary" disabled>Speichern</button></FormActions></FormShell>};
export const OfflineStale = {render: () => <FormShell title="Reisebudget"><p role="status">Offline · Gespeicherter Stand</p><FormField label="Geplanter Betrag"><input readOnly value="12345,67 EUR"/></FormField></FormShell>};
export const Unavailable = {render: () => <FormShell title="Reisebudget"><ErrorSummary autoFocus={false} errors={[{id: 'retry-budget', message: 'Daten derzeit nicht verfügbar.'}]}/><button id="retry-budget" className="secondary">Erneut versuchen</button></FormShell>};
