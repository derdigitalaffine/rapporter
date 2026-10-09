import {defineConfig} from '@playwright/test';

export default defineConfig({
  testDir:'./e2e',
  timeout:30_000,
  expect:{timeout:6_000},
  fullyParallel:true,
  reporter:[['line'],['html',{outputFolder:'playwright-report',open:'never'}]],
  use:{
    baseURL:'http://127.0.0.1:4173',
    trace:'retain-on-failure',
    screenshot:'only-on-failure',
    video:'retain-on-failure',
    serviceWorkers:'allow',
  },
  projects:[
    {name:'mobile-chromium',use:{viewport:{width:390,height:844}}},
    {name:'desktop-chromium',use:{viewport:{width:1440,height:900}}},
  ],
  webServer:{
    command:'npm run preview -- --host 127.0.0.1 --port 4173',
    url:'http://127.0.0.1:4173',
    reuseExistingServer:!process.env.CI,
  },
});
