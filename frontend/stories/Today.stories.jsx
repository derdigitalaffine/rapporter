import React from 'react';
import {expect,userEvent,within} from 'storybook/test';
import {TodayOverviewContent} from '../src/TodayOverview';

export default {title:'FamilyOS/Today'};
const family={id:'fixture-family',timezone:'Europe/Berlin'};
const core={actions:[{id:'task:1',state:'overdue'}],events:[],loaded:true,actionFailed:false,calendarFailed:false};
const render=props=><TodayOverviewContent family={family} core={core} data={{overview:{shopping_open_count:12,pin_count:4}}} unreadMessages={2} {...props}/>;
export const Overview={render:()=>render(),play:async({canvasElement})=>{
 const canvas=within(canvasElement);
 const tasks=canvas.getByRole('link',{name:/Aufgaben/});
 await expect(canvas.getAllByRole('link')).toHaveLength(6);
 await expect(tasks).toHaveAttribute('href',expect.stringContaining('todo=today'));
 tasks.focus();
 await expect(tasks).toHaveFocus();
 await userEvent.tab();
 await expect(canvas.getByRole('link',{name:/Kalender/})).toHaveFocus();
}};
export const Loading={render:()=>render({core:{...core,loaded:false,loading:true},data:{},unreadMessages:null})};
export const PartialFailure={render:()=>render({core:{...core,actionFailed:true},unreadMessages:null})};
export const Empty={render:()=>render({core:{...core,actions:[]},data:{overview:{shopping_open_count:0,pin_count:0}},unreadMessages:0})};
export const LongValues={render:()=>render({language:'en',data:{overview:{shopping_open_count:123456,pin_count:12345}},unreadMessages:1234})};
