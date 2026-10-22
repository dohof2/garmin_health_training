import {useRef,type ReactNode} from 'react';

// Start a tab's work on its first visit; retain forms, plots and selections on
// later visits instead of unmounting them or preloading every hidden tab.
export default function RetainedPage({active,children}:{active:boolean;children:ReactNode}){
 const visited=useRef(false);
 if(active)visited.current=true;
 return <div hidden={!active}>{visited.current?children:null}</div>;
}
