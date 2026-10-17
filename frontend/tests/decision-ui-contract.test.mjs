import {readFileSync} from 'node:fs';
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {decisionNeedsVote,decisionResultState,decisionUrgency,filterDecisions,hasDecisionParticipation,sortDecisions} from '../src/decision-presentation.js';

const hub=readFileSync(new URL('../src/DecisionsHub.jsx',import.meta.url),'utf8');
const css=readFileSync(new URL('../src/decisions.css',import.meta.url),'utf8');

const NOW=Date.parse('2026-10-17T12:00:00Z');

test('open decisions are prioritized by missing action, then real deadlines',()=>{
  const rows=[
    {id:'closed',is_open:false},
    {id:'answered-soon',is_open:true,can_vote:true,my_option_ids:['a'],closes_at:'2026-10-17T14:00:00Z'},
    {id:'unanswered-later',is_open:true,can_vote:true,my_option_ids:[],closes_at:'2026-10-19T12:00:00Z'},
    {id:'unanswered-soon',is_open:true,can_vote:true,my_option_ids:[],closes_at:'2026-10-17T18:00:00Z'},
    {id:'no-deadline',is_open:true,can_vote:false},
  ];
  assert.deepEqual(sortDecisions(rows,NOW).map(row=>row.id),['unanswered-soon','unanswered-later','answered-soon','no-deadline','closed']);
  assert.equal(decisionNeedsVote(rows[2]),true);
  assert.equal(decisionNeedsVote(rows[1]),false);
  assert.equal(decisionUrgency(rows[3],NOW),'soon');
  assert.equal(decisionUrgency(rows[2],NOW),'upcoming');
  assert.equal(decisionUrgency(rows[4],NOW),'normal');
});

test('presentation filtering never mutates domain state or invents results',()=>{
  const rows=[{id:'a',is_open:true},{id:'b',is_open:false,result:{winner:{label:'B'}}}];
  assert.deepEqual(filterDecisions(rows,'open').map(row=>row.id),['a']);
  assert.deepEqual(filterDecisions(rows,'closed').map(row=>row.id),['b']);
  assert.deepEqual(filterDecisions(rows,'all').map(row=>row.id),['a','b']);
  assert.equal(decisionResultState(rows[1]),'winner');
  assert.equal(decisionResultState({is_open:false,result:{is_tie:true,winner:null}}),'tie');
});

test('participation derives only from canonical caller ballot fields',()=>{
  assert.equal(hasDecisionParticipation({mode:'single',my_option_ids:['x']}),true);
  assert.equal(hasDecisionParticipation({mode:'ranking',my_option_ids:[]}),false);
  assert.equal(hasDecisionParticipation({mode:'rating',options:[{my_score:null},{my_score:4}]}),true);
});

test('central composer consumes shared #400 form primitives and accessible validation',()=>{
  assert.match(hub,/ChoiceField,ErrorSummary,FormActions,FormField,FormRow,FormSection,FormShell,ProgressiveFieldGroup/);
  assert.match(hub,/noValidate/);
  assert.match(hub,/ErrorSummary errors=\{validationErrors\}/);
  assert.match(hub,/error=\{fieldError\(questionId\)\}/);
  assert.match(hub,/error=\{fieldError\(optionId\(index\)\)\}/);
  assert.match(hub,/cleanOptions\(draft\.options\)/);
});

test('smart UI is explainable and canonical-result driven',()=>{
  assert.match(hub,/filterHint:/);
  assert.match(hub,/sortDecisions\(rows\)/);
  assert.match(hub,/decisionUrgency\(row\)/);
  assert.match(hub,/row\?\.result\?\.winner/);
  assert.match(hub,/row\.result\.metric/);
  assert.doesNotMatch(hub,/Math\.(?:max|min)\([^\n]*votes/);
  assert.doesNotMatch(hub,/options\.sort\([^\n]*(?:votes|average_rank|average_score)/);
});

test('decision cards expose state in text and keep one local primary mutation',()=>{
  assert.match(hub,/hasMine\?w\.yourVoteSaved:interactive\?w\.yourVoteOpen:w\.readOnly/);
  assert.match(hub,/className="primary compact" onClick=\{\(\)=>saveVote\(row\)\}/);
  assert.match(hub,/className="secondary compact" onClick=\{\(\)=>saveVote\(row,\{clear:true\}\)\}/);
  assert.match(hub,/className="ghost ghost-danger compact" onClick=\{\(\)=>closeDecision\(row\)\}/);
});

test('decision CSS is tokenized, scoped, touch-safe and narrow-screen safe',()=>{
  for(const token of ['--color-border','--color-surface','--color-neutral-soft','--color-muted','--color-focus','--color-text','--space-2','--space-3','--space-4','--space-6','--radius-md'])assert.ok(css.includes(`var(${token})`),token);
  assert.doesNotMatch(css,/var\(--(?:muted|surface|surface-2|border),/);
  assert.doesNotMatch(css,/#[0-9a-f]{3,8}/i);
  assert.doesNotMatch(css,/!important/);
  assert.match(css,/\.decisions-hub \.decision-page-head/);
  assert.match(css,/\.decisions-hub \.decision-check/);
  assert.match(css,/\.decisions-hub \.decision-vote-option/);
  assert.match(css,/min-height:44px/);
  assert.match(css,/:focus-visible/);
  assert.match(css,/@media\(max-width:359px\)/);
  assert.match(css,/@media\(prefers-reduced-motion:reduce\)/);
});
