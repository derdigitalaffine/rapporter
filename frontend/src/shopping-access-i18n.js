import i18n from './i18n';

const resources={
  de:{
    audience:'Für wen?',family:'Ganze Familie',private:'Nur ich',selected:'Ausgewählte',
    selectedHint:'Wähle Personen oder eine Gruppe. Deine eigene Liste bleibt für dich erreichbar.',
    responsibility:'Wer kümmert sich?',responsibilityHint:'Optional – Zuständigkeit ändert keine Berechtigungen.',
    adults:'Erwachsene',children:'Kinder & Jugendliche',people:'Personen',loading:'Personen werden geladen …',
    unavailable:'Personen konnten nicht geladen werden.',accessSaved:'Freigabe gespeichert',access:'Für wen & Zuständigkeit',
    visibleTo:'Sichtbar für',responsible:'Zuständig',nobody:'Niemand fest zugeteilt',moreActions:'Mehr'
  },
  en:{
    audience:'Who is this for?',family:'Whole family',private:'Only me',selected:'Selected people',
    selectedHint:'Choose people or a group. Your own list always remains available to you.',
    responsibility:'Who is taking care of it?',responsibilityHint:'Optional – responsibility does not change access permissions.',
    adults:'Adults',children:'Children & teens',people:'People',loading:'Loading people …',
    unavailable:'People could not be loaded.',accessSaved:'Sharing saved',access:'Audience & responsibility',
    visibleTo:'Visible to',responsible:'Responsible',nobody:'Nobody assigned',moreActions:'More'
  },
  fr:{
    audience:'Pour qui ?',family:'Toute la famille',private:'Moi uniquement',selected:'Personnes sélectionnées',
    selectedHint:'Choisissez des personnes ou un groupe. Votre propre liste reste toujours accessible.',
    responsibility:'Qui s’en occupe ?',responsibilityHint:'Facultatif – la responsabilité ne modifie pas les droits d’accès.',
    adults:'Adultes',children:'Enfants et ados',people:'Personnes',loading:'Chargement des personnes …',
    unavailable:'Impossible de charger les personnes.',accessSaved:'Partage enregistré',access:'Visibilité et responsabilité',
    visibleTo:'Visible pour',responsible:'Responsable',nobody:'Personne assignée',moreActions:'Plus'
  },
  nl:{
    audience:'Voor wie?',family:'Hele gezin',private:'Alleen ik',selected:'Geselecteerde personen',
    selectedHint:'Kies personen of een groep. Je eigen lijst blijft altijd voor jou beschikbaar.',
    responsibility:'Wie regelt dit?',responsibilityHint:'Optioneel – verantwoordelijkheid verandert de toegangsrechten niet.',
    adults:'Volwassenen',children:'Kinderen & tieners',people:'Personen',loading:'Personen laden …',
    unavailable:'Personen konden niet worden geladen.',accessSaved:'Delen opgeslagen',access:'Zichtbaarheid & verantwoordelijkheid',
    visibleTo:'Zichtbaar voor',responsible:'Verantwoordelijk',nobody:'Niemand toegewezen',moreActions:'Meer'
  },
  th:{
    audience:'สำหรับใคร?',family:'ทั้งครอบครัว',private:'เฉพาะฉัน',selected:'คนที่เลือก',
    selectedHint:'เลือกสมาชิกหรือกลุ่ม รายการของคุณยังคงเข้าถึงได้สำหรับคุณเสมอ',
    responsibility:'ใครเป็นคนดูแล?',responsibilityHint:'ไม่บังคับ – ผู้รับผิดชอบไม่ได้เปลี่ยนสิทธิ์การเข้าถึง',
    adults:'ผู้ใหญ่',children:'เด็กและวัยรุ่น',people:'สมาชิก',loading:'กำลังโหลดสมาชิก …',
    unavailable:'ไม่สามารถโหลดสมาชิกได้',accessSaved:'บันทึกการแชร์แล้ว',access:'ผู้ที่มองเห็นและผู้รับผิดชอบ',
    visibleTo:'มองเห็นได้โดย',responsible:'ผู้รับผิดชอบ',nobody:'ยังไม่ได้กำหนดผู้รับผิดชอบ',moreActions:'เพิ่มเติม'
  }
};
for(const [language,values] of Object.entries(resources))i18n.addResourceBundle(language,'translation',{shoppingAccess:values},true,true);