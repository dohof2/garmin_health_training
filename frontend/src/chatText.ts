// Chat uses plain paragraphs. Remove paired emphasis markers, preserving code.
export function plainChatText(value:string){
 return value.split(/(```[\s\S]*?```|`[^`\n]*`)/g).map(part=>part.startsWith('`')?part:part.replace(/\*\*([^*]+?)\*\*/g,'$1').replace(/__([^_]+?)__/g,'$1')).join('');
}
