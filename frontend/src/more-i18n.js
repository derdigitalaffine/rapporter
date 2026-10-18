import i18n from './create-i18n';

const resources={
 de:{family:'Familie & Alltag',householdFinance:'Haushalt & Finanzen',administration:'Einstellungen & Verwaltung',legacyHome:'Alter Legacy-Startscreen',customize:'Anpassen',done:'Fertig',dragLabel:'{{title}} verschieben. Ziehen oder Pfeiltasten hoch/runter verwenden.',moved:'{{title}} auf Position {{position}} von {{total}} verschoben.'},
 en:{family:'Family & everyday life',householdFinance:'Household & finances',administration:'Settings & administration',legacyHome:'Legacy start screen',customize:'Customize',done:'Done',dragLabel:'Reorder {{title}}. Drag or use the up/down arrow keys.',moved:'{{title}} moved to position {{position}} of {{total}}.'},
 fr:{family:'Famille & quotidien',householdFinance:'Foyer & finances',administration:'Paramètres & administration',legacyHome:'Ancien écran d’accueil',customize:'Personnaliser',done:'Terminé',dragLabel:'Réorganiser {{title}}. Faites glisser ou utilisez les flèches haut/bas.',moved:'{{title}} déplacé à la position {{position}} sur {{total}}.'},
 nl:{family:'Gezin & dagelijks leven',householdFinance:'Huishouden & financiën',administration:'Instellingen & beheer',legacyHome:'Oud startscherm',customize:'Aanpassen',done:'Klaar',dragLabel:'{{title}} verplaatsen. Sleep of gebruik de pijltjestoetsen omhoog/omlaag.',moved:'{{title}} verplaatst naar positie {{position}} van {{total}}.'},
 th:{family:'ครอบครัวและชีวิตประจำวัน',householdFinance:'บ้านและการเงิน',administration:'การตั้งค่าและการจัดการ',legacyHome:'หน้าจอเริ่มต้นแบบเดิม',customize:'ปรับแต่ง',done:'เสร็จสิ้น',dragLabel:'จัดลำดับ {{title}} ใหม่ ลากหรือใช้ปุ่มลูกศรขึ้น/ลง',moved:'ย้าย {{title}} ไปยังตำแหน่ง {{position}} จาก {{total}} แล้ว'}
};

for(const [language,values] of Object.entries(resources))i18n.addResourceBundle(language,'translation',{moreUi:values},true,true);
export default i18n;
