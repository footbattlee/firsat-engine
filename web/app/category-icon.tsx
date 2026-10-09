export function CategoryIcon({kind}:{kind:string}) {
 const paths:Record<string,React.ReactNode>={
 device:<><rect x="3" y="4" width="18" height="13" rx="2"/><path d="M8 21h8m-4-4v4"/></>,
 home:<><path d="m3 10 9-7 9 7M5 9v12h14V9"/><path d="M9 21v-7h6v7"/></>,
 spark:<><path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/></>,
 baby:<><circle cx="12" cy="13" r="8"/><path d="M12 5c-4-4 3-5 3-2M8 12h.01M16 12h.01m-8 4c2 2 6 2 8 0"/></>,
 basket:<><path d="m7 9 5-6 5 6M3 9h18l-2 12H5ZM9 12v6m6-6v6"/></>,
 heart:<path d="M20 5c-4-4-8 2-8 2S8 1 4 5c-5 5 8 16 8 16S25 10 20 5Z"/>,
 ball:<><circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c-5 5-5 13 0 18M12 3c5 5 5 13 0 18"/></>,
 book:<><path d="M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1Zm0 0v15"/></>,
 shirt:<path d="m8 3-5 3-2 5 5 2v8h12v-8l5-2-2-5-5-3c0 4-8 4-8 0Z"/>,
 grid:<><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></>
 };
 return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[kind]||paths.grid}</svg>;
}
