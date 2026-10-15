import i18n from './i18n';

const resources={
 de:{running:'Einkauf läuft',together:'Gemeinsam mit {{names}}',remoteChecked:'{{name}} hat {{item}} abgehakt',remoteReopened:'{{name}} hat {{item}} wieder geöffnet',remoteAdded:'{{name}} hat {{item}} ergänzt',syncIssue:'Live-Abgleich gerade nicht verfügbar'},
 en:{running:'Shopping in progress',together:'Shopping with {{names}}',remoteChecked:'{{name}} checked off {{item}}',remoteReopened:'{{name}} reopened {{item}}',remoteAdded:'{{name}} added {{item}}',syncIssue:'Live sync is temporarily unavailable'},
 fr:{running:'Courses en cours',together:'Courses avec {{names}}',remoteChecked:'{{name}} a coché {{item}}',remoteReopened:'{{name}} a rouvert {{item}}',remoteAdded:'{{name}} a ajouté {{item}}',syncIssue:'La synchronisation en direct est momentanément indisponible'},
 nl:{running:'Boodschappen bezig',together:'Samen met {{names}}',remoteChecked:'{{name}} heeft {{item}} afgevinkt',remoteReopened:'{{name}} heeft {{item}} heropend',remoteAdded:'{{name}} heeft {{item}} toegevoegd',syncIssue:'Live synchronisatie is tijdelijk niet beschikbaar'},
 th:{running:'กำลังซื้อของ',together:'ซื้อของร่วมกับ {{names}}',remoteChecked:'{{name}} ทำเครื่องหมาย {{item}} แล้ว',remoteReopened:'{{name}} เปิด {{item}} อีกครั้ง',remoteAdded:'{{name}} เพิ่ม {{item}}',syncIssue:'การซิงก์แบบสดไม่พร้อมใช้งานชั่วคราว'},
};
for(const [language,values] of Object.entries(resources))i18n.addResourceBundle(language,'translation',{shoppingSession:values},true,true);
