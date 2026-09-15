#!/bin/bash
# 티스토리 편집기에 DKAPTCHA 가 떠 있는지 본다. 있으면 "y", 없으면 "n".
#   사용: captcha_check.sh <글번호>
# ⚠️ DKAPTCHA 는 **iframe 안**에 그려진다(2026-09-07 실측).
#    최상위 document 의 innerText·input.placeholder 만 보면 절대 못 찾는다.
#    "정답을 입력해주세요" 는 placeholder 속성이라 innerText 에도 안 잡힌다 — 이중으로 안 보인다.
export PATH="$HOME/.local/bin:$PATH"
ID="${1:?글번호}"
cd /tmp
aside repl "
const t=(await listBrowserTabs()).find(x=>x.url.includes('newpost/${ID}'));
if(!t){ console.log('RESULT=notab'); } else {
  const p=await attachBrowserTab(t.targetId);
  let hit=false;
  // ① 최상위 문서 신호: 발행 버튼이 '저장중' 에서 멈춰 있으면 캡챠에 막힌 것이다.
  //    캡챠 iframe 이 **교차 출처면 evaluate 가 예외**로 막혀 프레임 순회로는 못 잡는다(2026-09-07 실측:
  //    화면엔 DKAPTCHA 가 떠 있는데 프레임 검사는 계속 n 을 반환했다).
  try {
    const top = await p.evaluate(()=>[...document.querySelectorAll('button')].some(b=>(b.innerText||'').trim()==='저장중'));
    if (top) hit = true;
  } catch(e){}
  for (const f of p.frames()) {
    if (hit) break;
    try {
      const r=await f.evaluate(()=>{
        const t=document.body?document.body.innerText||'':'';
        const ph=[...document.querySelectorAll('input')].some(i=>/정답을 입력/.test(i.placeholder||''));
        return ph || /DKAPTCHA|지도에서 아래 장소|빈칸에 들어갈/.test(t);
      });
      if(r){ hit=true; break; }
    } catch(e){}
  }
  console.log('RESULT='+(hit?'y':'n'));
}
" 2>/dev/null | grep '^RESULT=' | sed 's/RESULT=//'
