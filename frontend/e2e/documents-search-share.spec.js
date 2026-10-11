import {test,expect} from '@playwright/test';
import {installApiMocks} from './mock-api.js';

test('PWA manifest accepts multiple supported document files',async({request})=>{
 const response=await request.get('/manifest.webmanifest');
 expect(response.ok()).toBeTruthy();
 const manifest=await response.json();
 expect(manifest.share_target.method).toBe('POST');
 expect(manifest.share_target.enctype).toBe('multipart/form-data');
 const fileTarget=manifest.share_target.params.files[0];
 expect(fileTarget.name).toBe('files');
 expect(fileTarget.accept).toEqual(expect.arrayContaining(['application/pdf','image/jpeg','image/png','image/webp']));
});

test('document inbox exposes authorized search and normal multi-file fallback',async({page})=>{
 await installApiMocks(page,{dismissOnboarding:true});
 await page.route('**/api/documents/search/**',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({count:1,results:[{id:'doc-1',family:'family-1',title:'Beitragsbescheid',kind:'letter',document_date:'2026-10-04',correspondent:'AOK',visibility:'family',owner_membership:'member-1',processing_status:'ready',pinned:false,snippet:'Ihre Unterlagen reichen Sie bitte ein.',file_url:'/api/documents/doc-1/file/',can_manage:true}]})}));
 await page.goto('/?page=documents');
 await page.waitForLoadState('networkidle');
 await expect(page.getByRole('heading',{name:'Dokumente',exact:true})).toBeVisible();
 await expect(page.getByText('Beitragsbescheid')).toBeVisible();
 await expect(page.getByText(/Ihre Unterlagen/)).toBeVisible();
 const input=page.locator('input[type=file]');
 await input.setInputFiles([
  {name:'brief-a.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4 test-a')},
  {name:'brief-b.pdf',mimeType:'application/pdf',buffer:Buffer.from('%PDF-1.4 test-b')},
 ]);
 await expect(page.locator('.documents-pending-row')).toHaveCount(2);
 await expect(page.getByRole('button',{name:/2 Dokumente importieren/})).toBeVisible();
});
