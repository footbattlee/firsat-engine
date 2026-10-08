"use client";
import {useEffect,useRef} from "react";
export function VisitCounter() {
 const sent=useRef(false);
 useEffect(()=>{
  function visit() {
   if(sent.current||document.visibilityState!=="visible")return;
   sent.current=true;
   void fetch("/api/visit",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({path:"/"}),keepalive:true}).catch(()=>{});
  }
  visit();document.addEventListener("visibilitychange",visit);
  return ()=>document.removeEventListener("visibilitychange",visit);
 },[]);
 return null;
}
