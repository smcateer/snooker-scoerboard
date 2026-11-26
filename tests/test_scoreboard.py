#!/usr/bin/env python3
"""Chromium integration/regression tests for the Snooker Scoreboard.

Run from the repository root: python tests/test_scoreboard.py
Requires: pip install -r requirements-dev.txt && python -m playwright install chromium
A test-only JS hook is injected into an in-memory HTML copy.
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'scorecard.html'
REPORT = ROOT / 'test-results' / 'results.json'

html = SOURCE.read_text()
anchor = '  render();\n})();'
assert html.count(anchor) == 1
hook = '''
  window.__test = {
    reset:()=>{state=newState();undoStack=[];mode='normal';render()},
    set:(patch)=>{state=Object.assign(newState(),clone(patch));mode='normal';render()},
    get:()=>({state:clone(state),balance:balance(),mode,buttons:[...document.querySelectorAll('#balls button')].map(b=>b.className),target:String(Math.floor(balance().total/2)+1),win:{a:document.querySelector('#target-a').textContent,b:document.querySelector('#target-b').textContent,markerX:document.querySelector('#marker').getBoundingClientRect().left,domainCenter:(document.querySelector('#domain').getBoundingClientRect().left+document.querySelector('#domain').getBoundingClientRect().right)/2,numberCenter:(document.querySelector('#target-number').getBoundingClientRect().left+document.querySelector('#target-number').getBoundingClientRect().right)/2,provisionalCount:document.querySelectorAll('.hatch').length}}),
    oldUndo:()=>{const old=clone(state);delete old.names;undoStack.push(old);render()},
  };
  render();
})();'''
html = html.replace(anchor, hook)

results=[]
def check(name, observed, expected, category='scoring', note=''):
    ok = observed == expected
    results.append({'scenario':name,'category':category,'pass':ok,'expected':expected,'observed':observed,'note':note})
    return ok

def skip(name, note):
    results.append({'scenario':name,'category':'unsupported','pass':None,'expected':'not implemented','observed':'not implemented','note':note})

async def state(page):
    return await page.evaluate('window.__test.get()')

async def reset(page, **patch):
    if patch:
        await page.evaluate('(s)=>window.__test.set(s)',patch)
    else:
        await page.evaluate('window.__test.reset()')

async def clicks(page, *selectors):
    await page.evaluate('''(selectors) => {
      for (const css of selectors) {
        const btn=document.querySelector(css);
        if(!btn) throw new Error('No matching control: '+css);
        if(btn.disabled) throw new Error('Disabled control: '+css);
        btn.click();
      }
    }''',list(selectors))

async def edit(page, selector, value):
    await page.locator('#settings').click()
    await page.locator(selector).fill(str(value))
    await page.locator(selector).dispatch_event('change')
    await page.locator('[data-close="edit-dialog"]').click()

async def main():
 async with async_playwright() as p:
  import shutil
  binary=shutil.which('chromium') or shutil.which('chromium-browser') or shutil.which('google-chrome')
  launch_args={'headless':True,'args':['--no-sandbox','--disable-dev-shm-usage']}
  if binary: launch_args['executable_path']=binary
  browser=await p.chromium.launch(**launch_args)
  page=await browser.new_page(viewport={'width':1366,'height':768})
  errors=[]
  page.on('pageerror',lambda err: errors.append(str(err)))
  await page.set_content(html)

  s=await state(page)
  check('01. Initial frame 147 points',(s['state']['scores'],s['balance']['remain'],s['target']),([0,0],147,'74'))
  check('02. Red only button',s['buttons'],['ball-button red'])
  await clicks(page,'.ball-button.red')
  s=await state(page)
  check('03. Red scored, pending black', (s['state']['scores'],s['state']['reds'],s['state']['phase'],s['balance']['edge'],s['target']),([1,0],14,'choice',7,'74'))
  check('04. Colour order black first',[x.split(' ')[-1] for x in s['buttons']],['black','pink','blue','brown','green','yellow'])
  await clicks(page,'.ball-button.black')
  s=await state(page)
  check('05. Red+black returns to reds, unchanged target',(s['state']['scores'],s['state']['break'],s['state']['phase'],s['target']),([8,0],8,'reds','74'))

  await reset(page)
  await clicks(page,'.ball-button.red','.ball-button.yellow')
  s=await state(page)
  check('06. Yellow instead of black costs five possible points',(s['state']['scores'],s['balance']['total'],s['target']),([3,0],142,'72'))
  await reset(page)
  await clicks(page,'.ball-button.red','.ball-button.pink')
  s=await state(page)
  check('07. Pink instead of black costs one possible point',(s['state']['scores'],s['balance']['total'],s['target']),([7,0],146,'74'))

  await reset(page)
  await clicks(page,'.ball-button.red','#miss')
  s=await state(page)
  check('08. Miss after red forfeits colour and changes player',(s['state']['scores'],s['state']['striker'],s['state']['phase'],s['balance']['total'],s['target']),([1,0],1,'reds',140,'71'))
  await reset(page)
  await clicks(page,'#miss')
  s=await state(page)
  check('09. Miss before pot changes player only',(s['state']['striker'],s['state']['scores'],s['target']),(1,[0,0],'74'))
  await clicks(page,'.ball-button.red','.ball-button.black')
  s=await state(page)
  check('10. Player B scores on own visit',(s['state']['scores'],s['state']['break']),([0,8],8))
  await clicks(page,'#miss')
  s=await state(page)
  check('11. End of visit resets break',(s['state']['striker'],s['state']['break']),(0,0))

  await reset(page)
  await clicks(page,'#foul','[data-penalty="4"]')
  s=await state(page)
  check('12. 4-point foul credited to opponent',(s['state']['scores'],s['state']['striker'],s['state']['afterFoul'],s['balance']['total'],s['target']),([0,4],1,True,151,'76'))
  check('13. Post-foul choice replaces ordinary scoring controls',
      (await page.locator('#after-foul').is_visible(),await page.locator('#balls').is_visible()),(True,False),'workflow')
  await clicks(page,'#continue')
  s=await state(page)
  check('14. Continue from foul begins opponent visit',(s['state']['striker'],s['state']['afterFoul'],s['state']['freeBall']),(1,False,False))

  await reset(page)
  await clicks(page,'#foul','[data-penalty="7"]','#play-again')
  s=await state(page)
  check('15. Play again after foul: offender returns, 7 points held',(s['state']['scores'],s['state']['striker'],s['state']['afterFoul']),([0,7],0,False))

  await reset(page)
  await clicks(page,'#foul','[data-penalty="4"]','#call-free')
  s=await state(page)
  check('16. Free ball on reds adds 8-point striker opportunity',(s['state']['striker'],s['state']['freeBall'],s['balance']['edge'],s['balance']['total'],s['target']),(1,True,8,159,'80'))
  check('17. Free ball pot action appears','ball-button free' in s['buttons'],True,'workflow')
  await clicks(page,'.ball-button.free')
  s=await state(page)
  check('18. Free ball nominated red leaves reds unchanged',(s['state']['scores'],s['state']['reds'],s['state']['phase'],s['balance']['edge'],s['target']),([0,5],15,'choice',7,'80'))
  await clicks(page,'.ball-button.black')
  s=await state(page)
  check('19. Free red + colour produces 8 points, unchanged reds',(s['state']['scores'],s['state']['reds'],s['state']['phase'],s['target']),([0,12],15,'reds','80'))
  await reset(page)
  await clicks(page,'#foul','[data-penalty="5"]','#call-free','#miss')
  s=await state(page)
  check('20. Miss cancels unpotted free-ball opportunity',(s['state']['scores'],s['state']['striker'],s['state']['freeBall'],s['target']),([0,5],0,False,'77'))

  await reset(page)
  await clicks(page,'.ball-button.red')
  await reset(page,reds=1,phase='reds',scores=[40,37])
  await clicks(page,'.ball-button.red')
  s=await state(page)
  check('21. Last red leaves colour opportunity',(s['state']['phase'],s['state']['reds'],s['balance']['edge']),('choice',0,7))
  await clicks(page,'.ball-button.blue')
  s=await state(page)
  check('22. Colour after last red is respotted, then yellow on',(s['state']['phase'],s['state']['alive'],s['buttons']),('clearance',[2,3,4,5,6,7],['ball-button yellow']))
  await reset(page,reds=1,phase='reds')
  await clicks(page,'.ball-button.red','#miss')
  s=await state(page)
  check('23. Last red then miss starts clearance with yellow',(s['state']['phase'],s['state']['striker'],s['buttons']),('clearance',1,['ball-button yellow']))

  await reset(page)
  # Full 147, using 15 red/black pairs and colours in ascending order.
  await page.evaluate('''() => {
    for(let i=0;i<15;i++){
      document.querySelector('.ball-button.red').click();
      document.querySelector('.ball-button.black').click();
    }
    for(const name of ['yellow','green','brown','blue','pink','black']) document.querySelector('.ball-button.'+name).click();
  }''')
  s=await state(page)
  check('24. Complete 147 maximum break', (s['state']['scores'],s['state']['break'],s['state']['reds'],s['state']['alive'],s['state']['done']),([147,0],147,0,[],True))
  check('25. Finished frame hides scoring controls',await page.locator('#events').is_visible(),False,'workflow')
  await clicks(page,'#undo')
  s=await state(page)
  check('26. Undo final black restores live frame',(s['state']['scores'],s['state']['alive'],s['state']['done']),([140,0],[7],False),'undo')

  await reset(page,reds=0,phase='clearance',alive=[7],scores=[54,54],striker=0)
  await clicks(page,'.ball-button.black')
  s=await state(page)
  check('27. Final black pot normally finishes frame',(s['state']['scores'],s['state']['done']),([61,54],True))
  await reset(page,reds=0,phase='clearance',alive=[7],scores=[54,61],striker=0)
  await clicks(page,'.ball-button.black')
  s=await state(page)
  check('28. Tied final black starts playable re-spot',(s['state']['scores'],s['state']['done'],s['state']['alive']),([61,61],False,[7]),'rules','WPBSA rule 4: re-spotted black, not complete frame')
  await reset(page,reds=0,phase='clearance',alive=[7],scores=[51,58],striker=0)
  await clicks(page,'#foul','[data-penalty="7"]')
  s=await state(page)
  check('29. Foul with only black remains ends frame',(s['state']['scores'],s['state']['done']),([51,65],True),'rules','WPBSA rule 4: first foul on final black ends frame')
  await reset(page,reds=0,phase='clearance',alive=[7],scores=[51,58],striker=0)
  await clicks(page,'#foul','[data-penalty="7"]')
  s=await state(page)
  await reset(page,reds=0,phase='clearance',alive=[7],scores=[51,58])
  await clicks(page,'#foul')
  check('30. Black on: penalty 4 is not lawful',await page.locator('#foul-choice [data-penalty="4"]').is_visible(),False,'rules')

  await reset(page,reds=0,phase='clearance',alive=[7],scores=[58,51],striker=0)
  await clicks(page,'#foul','[data-penalty="7"]')
  s=await state(page)
  check('31. Foul on only black resulting in tie requires playable re-spot',(s['state']['scores'],s['state']['done'],s['state']['afterFoul'],s['state']['alive']),([58,58],False,False,[7]),'rules')

  await reset(page,reds=0,phase='clearance',alive=[2,3,4,5,6,7],scores=[25,20])
  await clicks(page,'#foul','[data-penalty="4"]','#call-free')
  s=await state(page)
  check('32. Free ball when yellow on has value 2',(s['state']['freeBall'],s['balance']['edge'],s['target']),(True,2,'40'))
  await clicks(page,'.ball-button.free')
  s=await state(page)
  check('33. Free ball as yellow scored and re-spotted',(s['state']['scores'],s['state']['alive'],s['buttons']),([25,26],[2,3,4,5,6,7],['ball-button yellow']))

  await reset(page,reds=0,phase='clearance',alive=[7],scores=[57,60])
  await clicks(page,'#foul','[data-penalty="7"]')
  s=await state(page)
  check('34. Free-ball call not offered when only black remains',await page.locator('#call-free').is_visible(),False,'rules','Cannot be snookered on black by a non-on ball if black is sole object ball')

  await reset(page)
  await clicks(page,'.ball-button.red','#foul','[aria-label="Nominated yellow"]','[data-penalty="4"]')
  s=await state(page)
  check('35. Foul while on colour forfeits colour bonus',(s['state']['scores'],s['state']['phase'],s['state']['striker'],s['target']),([1,4],'reds',1,'73'))
  await reset(page)
  await clicks(page,'#foul')
  check('36. Foul menu displays four penalties',await page.locator('#foul-choice [data-penalty]').count(),4,'workflow')
  await clicks(page,'#cancel-foul')
  s=await state(page)
  check('37. Cancel foul leaves frame unchanged',(s['state']['scores'],s['state']['striker'],s['mode']),([0,0],0,'normal'),'workflow')

  await reset(page)
  await clicks(page,'.ball-button.red')
  await clicks(page,'#undo')
  s=await state(page)
  check('38. Undo red restores initial state',(s['state']['scores'],s['state']['reds'],s['state']['phase']),([0,0],15,'reds'),'undo')
  await reset(page)
  await clicks(page,'#foul','[data-penalty="4"]','#continue','#undo')
  s=await state(page)
  check('39. Undo post-foul decision restores pending choice',(s['state']['afterFoul'],s['state']['scores'],s['state']['striker']),(True,[0,4],1),'undo')

  await reset(page)
  await page.locator('#reset').click()
  await page.locator('#new-name-a').fill('Ronnie')
  await page.locator('#new-name-b').fill('John')
  await page.locator('[data-start="1"]').click()
  s=await state(page)
  check('40. New frame names and B starts',(s['state']['names'],s['state']['striker'],s['state']['scores']),(['Ronnie','John'],1,[0,0]),'workflow')
  check('41. Names appear under chart',(await page.locator('#name-a').inner_text(),await page.locator('#name-b').inner_text()),('Ronnie','John'),'workflow')
  await clicks(page,'.ball-button.red')
  await page.locator('#reset').click()
  await page.locator('[data-start="0"]').click()
  s=await state(page)
  check('42. New frame retains names, clears scores and history',(s['state']['names'],s['state']['scores'],s['state']['history']),(['Ronnie','John'],[0,0],[]),'workflow')

  await reset(page)
  await edit(page,'#edit-a','132')
  s=await state(page)
  check('43. Manual score correction changes displayed score',(s['state']['scores'],await page.locator('#score-a').inner_text()),([132,0],'132'),'workflow')
  await edit(page,'#edit-a','-1')
  s=await state(page)
  check('44. Negative manual score rejected',s['state']['scores'],[132,0],'validation')
  await edit(page,'#edit-reds','99')
  s=await state(page)
  check('45. Reds count greater than 15 rejected',s['state']['reds'],15,'validation')

  await reset(page,scores=[69,20],striker=0,reds=3,phase='choice')
  s=await state(page)
  check('46. Hatch crosses centre yet opponent still has scoring route',(s['balance']['reachB']>s['state']['scores'][0], s['balance']['total'],s['target']),(True,147,'74'),'visual semantics','A 69+7 conditional reaches 76; B can still reach 71 > 69')

  await reset(page)
  await page.evaluate('window.__test.oldUndo()')
  await clicks(page,'#undo')
  check('47. Legacy undo entry without names safely restored',len(errors)==0,True,'persistence', 'Older saved undo snapshots may lack names')

  await reset(page)
  await clicks(page,'.ball-button.red')
  await page.set_viewport_size({'width':1366,'height':768})
  await page.wait_for_timeout(220)
  d=await page.evaluate('''() => {
    const a=document.querySelector('#score-panel-a').getBoundingClientRect();
    const track=document.querySelector('#track').getBoundingClientRect();
    const b=document.querySelector('#score-panel-b').getBoundingClientRect();
    return {leftGap:track.left-a.right,rightGap:b.left-track.right,scroll:document.documentElement.scrollHeight>innerHeight};
  }''')
  check('48. Desktop bar gaps and no scroll',(d['leftGap']>=0,d['rightGap']>=0,d['scroll']),(True,True,False),'layout')
  await page.set_viewport_size({'width':375,'height':667})
  await page.wait_for_timeout(220)
  d=await page.evaluate('''() => {
    const a=document.querySelector('#score-panel-a').getBoundingClientRect();
    const track=document.querySelector('#track').getBoundingClientRect();
    const b=document.querySelector('#score-panel-b').getBoundingClientRect();
    return {leftGap:track.left-a.right,rightGap:b.left-track.right,scroll:document.documentElement.scrollHeight>innerHeight};
  }''')
  check('49. Mobile score gaps and no scroll',(d['leftGap']>=0,d['rightGap']>=0,d['scroll']),(True,True,False),'layout')

  # Long frames / randomized clickpaths to catch state errors.
  await page.set_viewport_size({'width':1366,'height':768})
  await reset(page)
  fuzz=await page.evaluate('''() => {
    const results=[];let seed=42;
    const rnd=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296};
    for(let scenario=0;scenario<200;scenario++){
      window.__test.reset();
      for(let k=0;k<130;k++){
        const candidates=[...document.querySelectorAll('#balls:not([hidden]) button,#actions:not([hidden]) button,#foul-choice:not([hidden]) button,#foul-nomination:not([hidden]) button,#after-foul:not([hidden]) button,#respot-choice:not([hidden]) button')];
        if(!candidates.length)break;
        const b=candidates[Math.floor(rnd()*candidates.length)];b.click();
        const s=window.__test.get(); const q=s.state; const t=s.balance;
        let why='';
        if(q.scores.some(n=>!Number.isInteger(n)||n<0))why='bad scores';
        else if(!Number.isInteger(q.reds)||q.reds<0||q.reds>15)why='bad reds';
        else if(q.alive.some((n,i)=> ![2,3,4,5,6,7].includes(n) || (i>0&&n<=q.alive[i-1])))why='bad colours';
        else if(t.total!==q.scores[0]+q.scores[1]+t.remain+t.edge)why='accounting mismatch';
        else if(Number(s.target)!==Math.floor(t.total/2)+1)why='target mismatch';
        else if(q.done&&q.alive.length!==0)why='completed with colours on table';
        if(why){results.push({scenario,step:k,why,state:q});break;}
      }
    }
    return results;
  }''')
  check('50. 200 random frames × 130 events: state invariants',fuzz,[],'fuzzing')

  # Additional rule-matrix and extreme cases.
  await reset(page,reds=0,phase='clearance',alive=[5,6,7],scores=[18,13])
  await clicks(page,'#foul')
  check('51. Blue on: 4-point foul not possible',await page.locator('#foul-choice [data-penalty="4"]').is_visible(),False,'rules')
  await reset(page,reds=0,phase='clearance',alive=[6,7],scores=[18,13])
  await clicks(page,'#foul')
  check('52. Pink on: 4- or 5-point foul not possible',
        (await page.locator('#foul-choice [data-penalty="4"]').is_visible(),await page.locator('#foul-choice [data-penalty="5"]').is_visible()),(False,False),'rules')
  await reset(page,reds=0,phase='clearance',alive=[7],scores=[18,13])
  await clicks(page,'#foul')
  await page.evaluate("document.querySelector('[data-penalty=\"4\"]').click()")
  s=await state(page)
  blocked=s['state']['scores']==[18,13]
  await clicks(page,'[data-penalty="7"]')
  s=await state(page)
  check('53. Invalid black foul blocked; legal 7-point foul recorded',(blocked,s['state']['scores']),(True,[18,20]),'rules')

  # Maximum 155 break following a free ball nominated as red, and opponent's penalty.
  await reset(page)
  await clicks(page,'#foul','[data-penalty="4"]','#call-free','.ball-button.free','.ball-button.black')
  await page.evaluate('''() => {
    for(let i=0;i<15;i++){
      document.querySelector('.ball-button.red').click();
      document.querySelector('.ball-button.black').click();
    }
    for(const name of ['yellow','green','brown','blue','pink','black']) document.querySelector('.ball-button.'+name).click();
  }''')
  s=await state(page)
  check('54. Maximum 155 break following free ball',
        (s['state']['scores'],s['state']['break'],s['state']['done']),([0,159],155,True))

  await reset(page,reds=1,phase='reds')
  await clicks(page,'.ball-button.red','.ball-button.yellow')
  s=await state(page)
  check('55. Last red then yellow: remaining potential falls by five',
        (s['state']['scores'],s['state']['phase'],s['state']['alive'],s['balance']['total'],s['target']),
        ([3,0],'clearance',[2,3,4,5,6,7],30,'16'))

  await reset(page,reds=0,phase='clearance',alive=[7],scores=[20,0],names=['Ronnie','John'])
  await page.wait_for_timeout(250)
  geom=await page.evaluate('''() => {
    const a=document.querySelector('#name-a'),b=document.querySelector('#name-b'),t=document.querySelector('#track');
    return {nameA:a.clientWidth,fullNameA:a.scrollWidth,nameB:b.clientWidth,fullNameB:b.scrollWidth,track:t.getBoundingClientRect().width};
  }''')
  check('56. Names stay legible as remaining bar shrinks',
        (geom['nameA']>=geom['fullNameA'],geom['nameB']>=geom['fullNameB']),
        (True,True),'layout',str(geom))

  await reset(page,scores=[69,20],striker=0,reds=3,phase='choice')
  s=await state(page)
  hatchCrosses=(s['state']['scores'][0]+s['balance']['edge'] > s['balance']['total']/2)
  opponentNeedsSnookers=(s['balance']['reachB']<s['state']['scores'][0])
  check('57. Hatched crossing is provisional, not yet secured',
        (hatchCrosses,opponentNeedsSnookers),(True,False),'visual semantics',
        'A 69 + 7 provisional passes midpoint, but B has 20 + 51 shared = 71, more than 69')
  await clicks(page,'.ball-button.black')
  s=await state(page)
  check('71. Potting black converts provisional lead into snookers',
        (s['state']['scores'],s['balance']['reachB']<s['state']['scores'][0],s['target']),
        ([76,20],True,'74'),'visual semantics')

  await reset(page)
  await clicks(page,'.ball-button.red')
  await page.evaluate('''() => {
    for(const name of ['black','red']) {
      const button=document.querySelector('.ball-button.'+name);
      if(button) button.click();
    }
  }''')
  s=await state(page)
  check('58. Ordinary sequence cannot pot two reds consecutively',s['state']['scores'],[9,0])

  await reset(page)
  await edit(page,'#edit-a','1000')
  s=await state(page)
  check('59. Manual score above 999 rejected',s['state']['scores'],[0,0],'validation')

  await reset(page)
  await clicks(page,'#foul','[data-penalty="4"]','#play-again','.ball-button.red')
  s=await state(page)
  check('60. Playing again after foul allows offender to score',
        (s['state']['scores'],s['state']['striker'],s['state']['phase']),([1,4],0,'choice'))

  await reset(page)
  await clicks(page,'#foul','[data-penalty="4"]','#call-free','#miss')
  s=await state(page)
  check('61. Unpotted free ball does not consume a red',s['state']['reds'],15)

  await reset(page,reds=0,phase='clearance',alive=[2,3,4,5,6,7])
  await clicks(page,'.ball-button.yellow','#miss')
  s=await state(page)
  check('62. Miss during colour clearance preserves next colour',(s['state']['striker'],s['state']['alive'],s['buttons']),(1,[3,4,5,6,7],['ball-button green']))

  await reset(page)
  await clicks(page,'#foul','[data-penalty="4"]','#call-free','.ball-button.free','#miss')
  s=await state(page)
  check('63. Free-red then missing colour: no red consumed, bonus lost',
        (s['state']['scores'],s['state']['reds'],s['state']['phase'],s['state']['striker']),
        ([0,5],15,'reds',0))

  await reset(page)
  await clicks(page,'#foul','[data-penalty="4"]','#call-free')
  s=await state(page)
  check('64. When free ball is on, its button has accessible name',
        await page.locator('.ball-button.free').get_attribute('aria-label'),'Pot nominated free ball','accessibility')

  await reset(page)
  await clicks(page,'#miss','#miss','#miss','#miss','#miss')
  s=await state(page)
  check('65. Repeated ordinary misses leave scores, reds, target unchanged',
        (s['state']['scores'],s['state']['reds'],s['target'],s['state']['striker']),([0,0],15,'74',1))

  await reset(page,reds=0,phase='clearance',alive=[7],scores=[1,1])
  await clicks(page,'#miss')
  s=await state(page)
  check('66. On final black, unscored visit switches striker without finishing',
        (s['state']['striker'],s['state']['done'],s['state']['alive']),(1,False,[7]))

  await reset(page)
  await clicks(page,'#foul','[data-penalty="4"]','#play-again')
  await clicks(page,'#miss')
  s=await state(page)
  check('67. After offender plays again and misses, turn goes to non-offender',
        (s['state']['scores'],s['state']['striker']),([0,4],1))

  await reset(page,reds=0,phase='clearance',alive=[2,3,4,5,6,7])
  await clicks(page,'#foul','[data-penalty="4"]','#call-free')
  s=await state(page)
  check('68. Free ball available on first clearance colour',s['buttons'],['ball-button yellow','ball-button free'])

  # Explicit scope exclusions, not failures of implemented functionality.
  skip('69. Foul-and-a-miss restore-position option',
       'Restoration of ball positions following a foul-and-a-miss is not yet implemented.')
  skip('70. Multiple reds in one stroke',
       'The current UI records one red per pot; multiple reds in a stroke are not yet implemented.')

  # Real application save/reload code paths, with a deterministic localStorage
  # stand-in because headless Chromium blocks all local/HTTP origins here.
  await page.evaluate('''() => {
    window.__memory={};
    Object.defineProperty(window,'localStorage',{configurable:true,
      value:{getItem:k=>window.__memory[k]??null,setItem:(k,v)=>{window.__memory[k]=v}}});
  }''')
  await page.set_content(html)
  await clicks(page,'.ball-button.red')
  await page.set_content(html)
  s=await state(page)
  check('72. Save/reload retains pending colour and scores',
        (s['state']['scores'],s['state']['phase'],s['state']['reds']),([1,0],'choice',14),'persistence')
  check('73. Undo stack survives reload',await page.locator('#undo').is_enabled(),True,'persistence')
  await clicks(page,'#undo')
  s=await state(page)
  check('74. Undo works after reload',(s['state']['scores'],s['state']['phase']),([0,0],'reds'),'persistence')

  await page.locator('#reset').click()
  await page.locator('#new-name-a').fill('Mary')
  await page.locator('#new-name-b').fill('Steve')
  await page.locator('[data-start="1"]').click()
  await page.set_content(html)
  s=await state(page)
  check('75. Player names and starter survive reload',
        (s['state']['names'],s['state']['striker']),(['Mary','Steve'],1),'persistence')

  await clicks(page,'#foul','[data-penalty="4"]')
  await page.set_content(html)
  s=await state(page)
  check('76. Pending foul decision survives reload',
        (s['state']['afterFoul'],s['state']['offender'],await page.locator('#after-foul').is_visible()),
        (True,1,True),'persistence')

  await page.evaluate('''() => {window.__memory.snooker_ui_v6='not JSON';}''')
  await page.set_content(html)
  s=await state(page)
  check('77. Corrupt saved state safely falls back to new frame',
        (s['state']['scores'],s['state']['reds']),([0,0],15),'persistence')

  await page.set_viewport_size({'width':320,'height':568})
  await reset(page)
  await clicks(page,'.ball-button.red')
  layout=await page.evaluate('''() => ({
    scrollY:document.documentElement.scrollHeight>innerHeight,
    scrollX:document.documentElement.scrollWidth>innerWidth,
    buttons:[...document.querySelectorAll('#balls button')].length,
    lastBallInside:document.querySelector('#balls button:last-child').getBoundingClientRect().right<=innerWidth
  })''')
  check('78. 320×568 with six colours fits one screen',
        (layout['scrollY'],layout['scrollX'],layout['buttons'],layout['lastBallInside']),
        (False,False,6,True),'layout')

  await reset(page)
  await clicks(page,'#foul','[data-penalty="4"]')
  layout=await page.evaluate('''() => ({
    scrollY:document.documentElement.scrollHeight>innerHeight,
    scrollX:document.documentElement.scrollWidth>innerWidth,
    controls:document.querySelector('#after-foul').getBoundingClientRect().bottom<=innerHeight
  })''')
  check('79. 320×568 post-foul options fit one screen',
        (layout['scrollY'],layout['scrollX'],layout['controls']),
        (False,False,True),'layout')

  await reset(page,scores=[100,132],reds=0,phase='clearance',alive=[2,3,4,5,6,7],names=['Kyren','John'])
  await page.wait_for_timeout(220)
  geom=await page.evaluate('''() => {
    const a=document.querySelector('#score-panel-a').getBoundingClientRect();
    const b=document.querySelector('#score-panel-b').getBoundingClientRect();
    const bar=document.querySelector('#track').getBoundingClientRect();
    return {inside:a.left>=0&&b.right<=innerWidth,spaced:a.right<=bar.left&&b.left>=bar.right,scroll:document.documentElement.scrollWidth>innerWidth};
  }''')
  check('80. 320px width with two three-digit scores',
        (geom['inside'],geom['spaced'],geom['scroll']),(True,True,False),'layout')

  # v9-specific correctness tests: fully playable re-spotted black, nominated
  # colour foul penalties, undo/persistence, and responsive new controls.
  await page.set_viewport_size({'width':1366,'height':768})
  await reset(page,reds=0,phase='clearance',alive=[7],scores=[54,61],striker=0)
  await clicks(page,'.ball-button.black')
  s=await state(page)
  check('81. Equalising final black offers a starter choice',
        (s['state']['phase'],s['state']['respotPending'],s['state']['alive'],await page.locator('#respot-choice').is_visible()),
        ('respotted',True,[7],True),'re-spotted black')
  await clicks(page,'[data-respot="1"]')
  s=await state(page)
  check('82. B starts re-spotted black with black on',
        (s['state']['striker'],s['state']['respotPending'],s['buttons']),(1,False,['ball-button black']),'re-spotted black')
  await clicks(page,'.ball-button.black')
  s=await state(page)
  check('83. Pot on re-spotted black completes frame',
        (s['state']['scores'],s['state']['done'],await page.locator('#events').is_visible()),
        ([61,68],True,False),'re-spotted black')
  await clicks(page,'#undo')
  s=await state(page)
  check('84. Undo winning pot restores playable re-spotted black',
        (s['state']['phase'],s['state']['scores'],s['state']['done'],s['buttons']),
        ('respotted',[61,61],False,['ball-button black']),'undo')
  await clicks(page,'#undo')
  s=await state(page)
  check('85. Undo starter selection returns to pending choice',
        (s['state']['respotPending'],await page.locator('#respot-choice').is_visible()),(True,True),'undo')
  await clicks(page,'#undo')
  s=await state(page)
  check('86. Undo tie restores final-black opportunity',
        (s['state']['scores'],s['state']['phase'],s['state']['alive']),([54,61],'clearance',[7]),'undo')

  await reset(page,reds=0,phase='clearance',alive=[7],scores=[54,61],striker=0)
  await clicks(page,'.ball-button.black','[data-respot="1"]','#miss')
  s=await state(page)
  check('87. Miss on re-spotted black switches player without ending frame',
        (s['state']['striker'],s['state']['done'],s['state']['phase']),(0,False,'respotted'),'re-spotted black')
  await clicks(page,'#foul','[data-penalty="7"]')
  s=await state(page)
  check('88. Foul on re-spotted black ends frame',
        (s['state']['scores'],s['state']['done'],s['state']['afterFoul']),([61,68],True,False),'re-spotted black')

  await reset(page,reds=0,phase='clearance',alive=[7],scores=[58,51],striker=0)
  await clicks(page,'#foul','[data-penalty="7"]')
  s=await state(page)
  check('89. Final-black foul yielding a tie requests re-spotted black',
        (s['state']['scores'],s['state']['phase'],s['state']['respotPending']),([58,58],'respotted',True),'re-spotted black')
  await clicks(page,'[data-respot="0"]','#foul','[data-penalty="7"]')
  s=await state(page)
  check('90. Foul after re-spot completes frame with no free-ball path',
        (s['state']['scores'],s['state']['done'],s['state']['afterFoul']),([58,65],True,False),'re-spotted black')

  for i,(colour,minp) in enumerate([('blue',5),('pink',6),('black',7)],start=91):
    await reset(page,reds=0,phase='clearance',alive=list(range(minp,8)) if minp>=5 else [5,6,7])
    # Alive list for pink/black is naturally ascending and consecutive.
    await clicks(page,'#foul')
    opts=await page.evaluate('''() => [...document.querySelectorAll('[data-penalty]')]
      .filter(b=>!b.hidden&&!b.disabled).map(b=>Number(b.dataset.penalty))''')
    check(f'{i}. {colour} ball-on enforces minimum foul {minp}',opts,list(range(minp,8)),'penalties')

  await reset(page)
  await clicks(page,'.ball-button.red','#foul')
  check('94. On colour after red, foul requests nomination before penalty',
        (await page.locator('#foul-nomination').is_visible(),await page.locator('#foul-choice').is_visible()),
        (True,False),'nomination')
  await clicks(page,'[aria-label="Nominated black"]')
  opts=await page.evaluate('''() => [...document.querySelectorAll('[data-penalty]')]
      .filter(b=>!b.hidden&&!b.disabled).map(b=>Number(b.dataset.penalty))''')
  check('95. Nominated black restricts penalty to seven',opts,[7],'nomination')
  await page.evaluate("document.querySelector('[data-penalty=\"4\"]').click()")
  s=await state(page)
  check('96. Direct attempt at four-point black-nominated foul is ignored',
        (s['state']['scores'],s['state']['phase']),([1,0],'choice'),'nomination')
  await clicks(page,'[data-penalty="7"]')
  s=await state(page)
  check('97. Black-nominated foul credits seven and ends colour opportunity',
        (s['state']['scores'],s['state']['phase'],s['state']['afterFoul']),([1,7],'reds',True),'nomination')

  await reset(page)
  await clicks(page,'.ball-button.red','#foul','[aria-label="Nominated yellow"]')
  opts=await page.evaluate('''() => [...document.querySelectorAll('[data-penalty]')]
      .filter(b=>!b.hidden&&!b.disabled).map(b=>Number(b.dataset.penalty))''')
  check('98. Nominated yellow allows penalties 4–7',opts,[4,5,6,7],'nomination')
  await clicks(page,'#cancel-foul')
  s=await state(page)
  check('99. Cancelling nominated foul preserves score and choice',
        (s['state']['scores'],s['state']['phase'],s['mode']),([1,0],'choice','normal'),'nomination')

  await page.set_viewport_size({'width':320,'height':568})
  await reset(page)
  await clicks(page,'.ball-button.red','#foul')
  await page.wait_for_timeout(220)
  dims=await page.evaluate('''() => ({
    scrollY:document.documentElement.scrollHeight>innerHeight,
    scrollX:document.documentElement.scrollWidth>innerWidth,
    visible:document.querySelector('#foul-nomination').getBoundingClientRect().bottom<=innerHeight,
    balls:[...document.querySelectorAll('#foul-nomination-balls button')].length
  })''')
  check('100. 320×568 nomination step fits without scrolling',
        (dims['scrollY'],dims['scrollX'],dims['visible'],dims['balls']),
        (False,False,True,6),'layout')
  await page.set_viewport_size({'width':1366,'height':768})

  await reset(page,reds=0,phase='clearance',alive=[7],scores=[54,61])
  await clicks(page,'.ball-button.black')
  await page.set_content(html)
  s=await state(page)
  check('101. Pending re-spotted-black choice persists across reload',
        (s['state']['phase'],s['state']['respotPending'],await page.locator('#respot-choice').is_visible()),
        ('respotted',True,True),'persistence')
  await clicks(page,'[data-respot="1"]')
  await page.set_content(html)
  s=await state(page)
  check('102. Re-spotted starter survives reload and remains playable',
        (s['state']['striker'],s['state']['respotPending'],s['buttons']),
        (1,False,['ball-button black']),'persistence')
  await clicks(page,'.ball-button.black')
  s=await state(page)
  check('103. Loaded re-spotted game finishes on next legal pot',
        (s['state']['scores'],s['state']['done']),([61,68],True),'persistence')

  # Fixed midpoint is always physically at the centre; only the solid scores
  # are plotted and the exact signed half-point gaps remain above the marker.
  await reset(page)
  s=await state(page)
  check('104. Fresh frame has two half-point gaps',
        (s['win']['a'],s['win']['b'],s['win']['provisionalCount']),
        ('73.5','73.5',0),'midpoint')
  await clicks(page,'.ball-button.red')
  s=await state(page)
  check('105. Red leaves the pending black unshaded',
        (s['state']['scores'],s['balance']['edge'],s['win']['a'],s['win']['b'],s['win']['provisionalCount']),
        ([1,0],7,'72.5','73.5',0),'midpoint')
  await clicks(page,'.ball-button.black')
  s=await state(page)
  check('106. Black scores eight total and keeps midpoint 73.5',
        (s['state']['scores'],s['win']['a'],s['win']['b']),
        ([8,0],'65.5','73.5'),'midpoint')
  await reset(page,reds=0,phase='clearance',scores=[40,27])
  s=await state(page)
  check('107. Clearance gaps from exact midpoint',
        (s['win']['a'],s['win']['b']),('7','20'),'midpoint')
  await reset(page,reds=0,phase='clearance',scores=[60,33])
  s=await state(page)
  check('108. Exactly at midpoint displays zero',
        (s['win']['a'],s['win']['b']),('0','27'),'midpoint')
  await reset(page,reds=0,phase='clearance',scores=[65,28])
  s=await state(page)
  check('109. Signed surplus at midpoint',
        (s['win']['a'],s['win']['b']),('+5','32'),'midpoint')
  await reset(page,reds=0,phase='clearance',scores=[28,65],striker=1)
  s=await state(page)
  check('110. Right player shares same fixed threshold',
        (s['win']['a'],s['win']['b']),('32','+5'),'midpoint')
  await reset(page,reds=5,phase='reds',scores=[46,19],striker=0)
  await clicks(page,'.ball-button.red')
  s=await state(page)
  check('111. Pending colour keeps the true total midpoint',
        (s['state']['scores'],s['balance']['edge'],s['win']['a'],s['win']['b']),
        ([47,19],7,'19','47'),'midpoint')
  await reset(page,reds=5,phase='reds',scores=[66,19],striker=0)
  s=await state(page)
  check('112. Before red: both gaps',
        (s['win']['a'],s['win']['b']),('10','57'),'midpoint')
  await clicks(page,'.ball-button.red')
  s=await state(page)
  check('113. After red: line remains centred, pending still unshaded',
        (s['win']['a'],s['win']['b'],s['win']['provisionalCount']),
        ('9','57',0),'midpoint')
  await reset(page,reds=5,phase='reds',scores=[72,19],striker=0)
  await clicks(page,'.ball-button.red')
  s=await state(page)
  check('114. Gap labels keep half points where appropriate',
        (s['win']['a'],s['win']['b']),('6','60'),'midpoint')
  await clicks(page,'.ball-button.black')
  s=await state(page)
  check('115. After pot gap is based on score alone',
        (s['state']['scores'][0],s['win']['a']), (80,'+1'),'midpoint')
  await reset(page,reds=5,phase='reds',scores=[72,19],striker=0)
  await clicks(page,'.ball-button.red','#miss')
  s=await state(page)
  check('116. Miss changes maximum total but never centre position',
        (s['state']['scores'],s['win']['a'],s['win']['b']),
        ([73,19],'2.5','56.5'),'midpoint')
  await reset(page,reds=5,phase='reds',scores=[19,72],striker=1)
  await clicks(page,'.ball-button.red')
  s=await state(page)
  check('117. Mirrored striker still shows two independent gaps',
        (s['win']['a'],s['win']['b']),('60','6'),'midpoint')
  await reset(page,reds=0,phase='clearance',scores=[29,0],alive=[2,3,4,5,6,7],striker=1)
  s=await state(page)
  check('118. 29-0 screenshot both midpoint gaps',
        (s['win']['a'],s['win']['b']),('+1','28'),'midpoint')
  await reset(page,reds=5,phase='reds',scores=[30,8],striker=0)
  s=await state(page)
  check('119. 30-8 screenshot both midpoint gaps',
        (s['win']['a'],s['win']['b']),('22.5','44.5'),'midpoint')
  await reset(page,reds=5,phase='reds',scores=[30,8],striker=1)
  await clicks(page,'.ball-button.red')
  await page.wait_for_timeout(250)
  s=await state(page)
  check('120. Fixed centre for right striker and pending red',
        (round(s['win']['markerX']-s['win']['domainCenter'],1),round(s['win']['numberCenter']-s['win']['domainCenter'],1)),
        (0.0,0.0),'midpoint')
  await reset(page)
  await page.wait_for_timeout(250)
  s=await state(page)
  check('121. Reset midpoint geometry remains fixed',
        (round(s['win']['markerX']-s['win']['domainCenter'],1),round(s['win']['numberCenter']-s['win']['domainCenter'],1)),
        (0.0,0.0),'midpoint')

  # tests at end where exceptions intentionally raised by corrupt legacy undo
  passed=sum(x['pass'] is True for x in results)
  failed=sum(x['pass'] is False for x in results)
  skipped=sum(x['pass'] is None for x in results)
  print(f'Executed {len(results)} scenarios; {passed} passed, {failed} failed, {skipped} unsupported')
  for r in results:
   print(('SKIP' if r['pass'] is None else ('PASS' if r['pass'] else 'FAIL')),r['scenario'])
   if r['pass'] is False: print('   expected:',r['expected'],' observed:',r['observed'])
  print('JS exceptions',errors)
  REPORT.parent.mkdir(parents=True,exist_ok=True)
  REPORT.write_text(json.dumps({'source':str(SOURCE),'scenarios':results,'js_exceptions':errors},indent=2,ensure_ascii=False))
  await browser.close()
  if failed or errors:
   raise SystemExit(f'FAIL: {failed} failed assertions, {len(errors)} JS exceptions (see {REPORT})')

if __name__=='__main__':
 asyncio.run(main())
