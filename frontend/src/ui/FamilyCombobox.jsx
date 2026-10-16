import {useId, useState} from 'react';
import {Combobox} from '@base-ui/react/combobox';
import '../form-primitives.css';
import './interaction-primitives.css';

// The existing EntityPicker value contract stays ID-based, including external search.
export default function FamilyCombobox({label, description, items = [], selectedIds = [], onChange, getItemId = item => item.id, getItemLabel = item => item.label ?? item.name ?? String(item.id), multiple = true, placeholder = 'Suchen …', emptyMessage = 'Keine Treffer', className = '', id: providedId, query: controlledQuery, onQueryChange, filterLocally = true, clearQueryOnChoose = true, selectionLabel, removeLabel = 'Entfernen', getRemoveLabel, disabled = false, loading = false, loadingMessage = 'Wird geladen …', error = ''}) {
  const generatedId = useId(), id = providedId || generatedId;
  const [internalQuery, setInternalQuery] = useState('');
  const query = controlledQuery === undefined ? internalQuery : controlledQuery;
  const setQuery = value => {if (controlledQuery === undefined) setInternalQuery(value); onQueryChange?.(value);};
  const selectedSet = new Set(selectedIds.map(String));
  const selected = items.filter(item => selectedSet.has(String(getItemId(item))));
  const available = items.filter(item => !selectedSet.has(String(getItemId(item))) && (!filterLocally || String(getItemLabel(item)).toLocaleLowerCase().includes(String(query || '').trim().toLocaleLowerCase())));
  const descriptionId = description ? `${id}-description` : undefined;
  return <div className={`entity-picker ${className}`}>
    <label htmlFor={id}>{label}</label>
    {description && <p id={descriptionId} className="entity-picker__description">{description}</p>}
    {selected.length > 0 && <ul className="entity-picker__selected" aria-label={selectionLabel || `${label}: Auswahl`}>
      {selected.map(item => <li key={String(getItemId(item))}><span>{getItemLabel(item)}</span><button type="button" className="secondary" disabled={disabled} aria-label={getRemoveLabel?.(item) ?? `${getItemLabel(item)} ${removeLabel}`} onClick={() => onChange?.(selectedIds.filter(value => String(value) !== String(getItemId(item))))}>{removeLabel}</button></li>)}
    </ul>}
    <Combobox.Root inline open items={available} filter={null} value={null} inputValue={query || ''} onInputValueChange={setQuery} disabled={disabled} itemToStringLabel={getItemLabel} onValueChange={item => {
      if (!item) return;
      onChange?.(multiple ? [...selectedIds, getItemId(item)] : [getItemId(item)]);
      if (clearQueryOnChoose) setQuery('');
    }}>
      <Combobox.Input id={id} placeholder={placeholder} aria-describedby={descriptionId} aria-invalid={error ? true : undefined}/>
      <div className="entity-picker__results" aria-busy={loading}>
        <Combobox.Status>{loading ? loadingMessage : error}</Combobox.Status>
        <Combobox.Empty className="entity-picker__empty">{loading || error ? null : emptyMessage}</Combobox.Empty>
        <Combobox.List>{available.map(item => <Combobox.Item className="entity-picker__option" key={String(getItemId(item))} value={item} disabled={loading || Boolean(error)}>{getItemLabel(item)}</Combobox.Item>)}</Combobox.List>
      </div>
    </Combobox.Root>
  </div>;
}
