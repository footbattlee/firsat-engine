export const SHARE_ORIGIN:string;
export function shareChannel(value:unknown):string;
export function encodeShareCode(deal:string,offer:string):string;
export function decodeShareCode(code:string):{deal:string;offer:string}|null;
export function brandedLink(data:{id:string;offer_id?:string;cheapest_offer_id?:string},channel:string):string;
export function captionHasDeal(caption:unknown,id:string):boolean;
