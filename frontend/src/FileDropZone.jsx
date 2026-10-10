import {useId,useRef,useState} from 'react';
import {Icon} from './icons';
import './file-drop-zone.css';

export default function FileDropZone({
 accept,
 capture,
 multiple=false,
 disabled=false,
 icon='upload',
 title,
 hint='',
 className='',
 onFiles,
}){
 const id=useId();
 const inputRef=useRef(null);
 const [dragging,setDragging]=useState(false);

 function emit(fileList){
  if(disabled)return;
  const files=Array.from(fileList||[]);
  if(!files.length)return;
  onFiles?.(multiple?files:files.slice(0,1));
  if(inputRef.current)inputRef.current.value='';
 }
 function drag(event){
  event.preventDefault();
  if(!disabled)setDragging(true);
 }
 function leave(event){
  if(!event.currentTarget.contains(event.relatedTarget))setDragging(false);
 }
 function drop(event){
  event.preventDefault();
  setDragging(false);
  emit(event.dataTransfer?.files);
 }

 return <label
  className={`file-drop-zone ${dragging?'is-dragging':''} ${disabled?'is-disabled':''} ${className}`.trim()}
  htmlFor={id}
  onDragEnter={drag}
  onDragOver={drag}
  onDragLeave={leave}
  onDrop={drop}
 >
  <input
   id={id}
   ref={inputRef}
   className="file-drop-zone__input"
   type="file"
   accept={accept}
   capture={capture}
   multiple={multiple}
   disabled={disabled}
   aria-label={title}
   onChange={event=>emit(event.target.files)}
  />
  <span className="file-drop-zone__icon" aria-hidden="true"><Icon name={icon} size={22}/></span>
  <span className="file-drop-zone__copy"><strong>{title}</strong>{hint&&<small>{hint}</small>}</span>
 </label>;
}
