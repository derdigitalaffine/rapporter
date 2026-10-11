import {Children,cloneElement,isValidElement,useEffect,useId,useMemo,useRef,useState} from 'react';
import './form-primitives.css';

const cx=(...values)=>values.filter(Boolean).join(' ');
const describedBy=(...ids)=>ids.filter(Boolean).join(' ')||undefined;

export function FormShell({title,description,children,className='',...props}){
  const titleId=useId();
  const descriptionId=useId();
  return <form className={cx('form-shell',className)} aria-labelledby={title?titleId:undefined} aria-describedby={description?descriptionId:undefined} {...props}>
    {(title||description)&&<header className="form-shell__head">
      {title&&<h1 id={titleId}>{title}</h1>}
      {description&&<p id={descriptionId}>{description}</p>}
    </header>}
    {children}
  </form>;
}

export function FormSection({legend,description,children,className='',...props}){
  const descriptionId=useId();
  return <fieldset className={cx('form-section',className)} aria-describedby={description?descriptionId:undefined} {...props}>
    <legend>{legend}</legend>
    {description&&<p className="form-section__description" id={descriptionId}>{description}</p>}
    <div className="form-section__body">{children}</div>
  </fieldset>;
}

export function FormField({label,description,error,children,id:providedId,required=false,className=''}){
  const generatedId=useId();
  const id=providedId||generatedId;
  const descriptionId=description?`${id}-description`:undefined;
  const errorId=error?`${id}-error`:undefined;
  const childProps={id,required,'aria-invalid':error?true:undefined,'aria-describedby':describedBy(descriptionId,errorId)};
  let control=children;
  if(typeof children==='function'){
    control=children(childProps);
  }else if(isValidElement(children)&&Children.count(children)===1){
    const child=Children.only(children);
    control=cloneElement(child,{
      ...child.props,
      id,
      required:required||child.props.required||undefined,
      'aria-describedby':describedBy(child.props['aria-describedby'],descriptionId,errorId),
      'aria-invalid':error?true:child.props['aria-invalid'],
    });
  }
  return <div className={cx('form-field',error&&'form-field--invalid',className)}>
    <label htmlFor={id}>{label}{required&&<span className="form-field__required" aria-hidden="true"> *</span>}</label>
    {description&&<p id={descriptionId} className="form-field__description">{description}</p>}
    {control}
    {error&&<p id={errorId} className="form-field__error" role="status">{error}</p>}
  </div>;
}

export function FormRow({children,className='',columns=2,...props}){
  return <div className={cx('form-row',className)} style={{'--form-row-columns':columns}} {...props}>{children}</div>;
}

export function FieldGroup({legend,description,children,className='',...props}){
  const descriptionId=useId();
  return <fieldset className={cx('field-group',className)} aria-describedby={description?descriptionId:undefined} {...props}>
    <legend>{legend}</legend>
    {description&&<p id={descriptionId} className="field-group__description">{description}</p>}
    <div className="field-group__body">{children}</div>
  </fieldset>;
}

export function ProgressiveFieldGroup({label,summary,children,defaultOpen=false,className=''}){
  const [open,setOpen]=useState(defaultOpen);
  const regionId=useId();
  return <section className={cx('progressive-field-group',className)}>
    <button type="button" className="progressive-field-group__toggle" aria-expanded={open} aria-controls={regionId} onClick={()=>setOpen(value=>!value)}>
      <span>{label}</span><span aria-hidden="true">{open?'−':'+'}</span>
    </button>
    {summary&&!open&&<p className="progressive-field-group__summary">{summary}</p>}
    <span className="form-sr-only" aria-live="polite">{open?`${label} eingeblendet`:`${label} ausgeblendet`}</span>
    {open&&<div id={regionId} className="progressive-field-group__body">{children}</div>}
  </section>;
}

export function FormActions({children,className='',...props}){
  return <div className={cx('form-actions',className)} {...props}>{children}</div>;
}

export function ErrorSummary({errors=[],title='Bitte prüfe die markierten Felder',className='',autoFocus=true}){
  const summaryRef=useRef(null);
  const titleId=useId();
  const signature=errors.map(error=>`${error.id}:${error.message}`).join('|');
  useEffect(()=>{
    if(autoFocus&&errors.length) summaryRef.current?.focus();
  },[autoFocus,signature,errors.length]);
  if(!errors.length)return null;
  function focusField(event,id){
    const field=document.getElementById(id);
    if(!field)return;
    event.preventDefault();
    field.focus({preventScroll:true});
    field.scrollIntoView({block:'center',behavior:'smooth'});
  }
  return <section ref={summaryRef} className={cx('error-summary',className)} tabIndex={-1} role="alert" aria-labelledby={titleId}>
    <strong id={titleId}>{title}</strong>
    <ul>{errors.map(error=><li key={`${error.id}-${error.message}`}><a href={`#${error.id}`} onClick={event=>focusField(event,error.id)}>{error.label?`${error.label}: `:''}{error.message}</a></li>)}</ul>
  </section>;
}

export function EntityPicker({
  label,
  description,
  items=[],
  selectedIds=[],
  onChange,
  getItemId=item=>item.id,
  getItemLabel=item=>item.label??item.name??String(item.id),
  multiple=true,
  placeholder='Suchen …',
  emptyMessage='Keine Treffer',
  className='',
  id:providedId,
}){
  const generatedId=useId();
  const id=providedId||generatedId;
  const resultsId=`${id}-results`;
  const descriptionId=description?`${id}-description`:undefined;
  const [query,setQuery]=useState('');
  const selectedSet=useMemo(()=>new Set(selectedIds.map(String)),[selectedIds]);
  const selected=items.filter(item=>selectedSet.has(String(getItemId(item))));
  const normalized=query.trim().toLocaleLowerCase();
  const available=items.filter(item=>!selectedSet.has(String(getItemId(item)))&&(!normalized||String(getItemLabel(item)).toLocaleLowerCase().includes(normalized)));
  function choose(item){
    const value=getItemId(item);
    onChange?.(multiple?[...selectedIds,value]:[value]);
    setQuery('');
  }
  function remove(item){
    const value=String(getItemId(item));
    onChange?.(selectedIds.filter(itemId=>String(itemId)!==value));
  }
  return <div className={cx('entity-picker',className)}>
    <label htmlFor={id}>{label}</label>
    {description&&<p id={descriptionId} className="entity-picker__description">{description}</p>}
    {selected.length>0&&<ul className="entity-picker__selected" aria-label={`${label}: Auswahl`}>
      {selected.map(item=><li key={String(getItemId(item))}><span>{getItemLabel(item)}</span><button type="button" className="secondary" aria-label={`${getItemLabel(item)} entfernen`} onClick={()=>remove(item)}>Entfernen</button></li>)}
    </ul>}
    <input id={id} type="search" value={query} placeholder={placeholder} aria-describedby={descriptionId} aria-controls={resultsId} onChange={event=>setQuery(event.target.value)}/>
    <div id={resultsId} className="entity-picker__results" aria-live="polite">
      {available.length?<ul>{available.map(item=><li key={String(getItemId(item))}><button type="button" className="entity-picker__option" onClick={()=>choose(item)}>{getItemLabel(item)}</button></li>)}</ul>:<p className="entity-picker__empty">{emptyMessage}</p>}
    </div>
  </div>;
}
