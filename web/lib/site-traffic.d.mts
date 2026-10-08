export function trafficKind(headers:Headers,eventType:string):string;
export function trafficEvent(headers:Headers,eventType:string,path:string,secret:string,now?:Date):{event_key:string;event_type:string;path:string;visitor_hash:string;request_kind:string};
