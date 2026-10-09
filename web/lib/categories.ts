export const CATEGORIES = [
 {id:"elektronik",name:"Elektronik",icon:"device"},
 {id:"ev-mutfak",name:"Ev & Mutfak",icon:"home"},
 {id:"kozmetik-bakim",name:"Kozmetik & Bakım",icon:"spark"},
 {id:"anne-bebek",name:"Anne & Bebek",icon:"baby"},
 {id:"supermarket",name:"Süpermarket",icon:"basket"},
 {id:"saglik",name:"Sağlık & Vitamin",icon:"heart"},
 {id:"spor-outdoor",name:"Spor & Outdoor",icon:"ball"},
 {id:"kitap-okul",name:"Kitap & Kırtasiye",icon:"book"},
 {id:"moda",name:"Moda & Aksesuar",icon:"shirt"},
 {id:"diger",name:"Diğer",icon:"grid"}
] as const;
export function categoryFor(title:string,existing="") {
 const text=(existing+" "+title).toLocaleLowerCase("tr").replace(/ı/g,"i").normalize("NFD").replace(/[\u0300-\u036f]/g,"");
 const rules:[string,RegExp][]=[
 ["anne-bebek",/bebek|gogus pompasi|biberon|emzik|puset|mama sandalyesi|pampers|prima|oyuncak|lego|organik pamuklu islak havlu/],
 ["kozmetik-bakim",/makyaj|allik|concealer|fondoten|ruj|lipstick|blush|mascara|maskara|kapat[ıi]ci|tiras|epil|lumea|sac|sampuan|cilt|parfum|goz alti|gunes krem|dus jel|nemlendirici|kirpik|dis fircasi|dis macunu|sudocrem|keratin/],
 ["saglik",/vitamin|redoxon|efervesan|takviye|magnezyum|omega|probiyotik|tansiyon|ates olcer/],
 ["elektronik",/kulaklik|kulaklig|yazici|headphone|earbud|freebuds|soundcore|telefon|tablet|bilgisayar|monitor|ssd|usb|flash|bellek|hafiza|power.?bank|hoparlor|sarz|sarj|kamera|televizyon|klavye|mouse|oyun konsol|hdmi|anker|kingston/],
 ["kitap-okul",/kitap|atlas|kirtasiye|kalem|defter|okul|fotokopi/],
 ["supermarket",/deterjan|yumusatici|camasir|temizlik|kagit|kagid|pecete|havlu|islak mendil|kahve|cikolata|findik|kakaolu|biskuvi|zeytinyagi|gida/],
 ["ev-mutfak",/termos|matara|stanley|bardak|kupa|kase|tabak|air.?fryer|fritoz|kettle|isitici|tencere|tava|mutfak|makine|supurge|utu|blender|mikser|koltuk|sandalye|yatak|nevresim|kampmate/],
 ["spor-outdoor",/spor|kamp|outdoor|fitness|dambil|pilates|yoga|bisiklet|futbol|basketbol|suluk/],
 ["moda",/tisort|t-shirt|gomlek|elbise|pantolon|ayakkabi|corap|canta|bileklik|kolye|saat/]
 ];
 return rules.find(([,rule])=>rule.test(text))?.[0]||"diger";
}
