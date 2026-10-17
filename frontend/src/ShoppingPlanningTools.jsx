import {useTranslation} from 'react-i18next';
import {Icon} from './icons';
import FamilySheet from './ui/FamilySheet';
import ShoppingTemplateTools from './ShoppingTemplateTools';
import './shopping-template-i18n';

export default function ShoppingPlanningTools({family,list,onClose,onChanged}){
 const {t}=useTranslation();
 return <FamilySheet labelledBy="shopping-planning-tools-title" onClose={onClose}>
  <div className="sheet-handle"/>
  <div className="sheet-head"><div><small>{t('shoppingTemplateUi.planningEyebrow')}</small><h2 id="shopping-planning-tools-title">{t('shoppingTemplateUi.open')}</h2></div><button type="button" className="sheet-close" onClick={onClose} aria-label={t('close')}><Icon name="close"/></button></div>
  <ShoppingTemplateTools familyId={family?.id} list={list} onChanged={onChanged}/>
 </FamilySheet>;
}
