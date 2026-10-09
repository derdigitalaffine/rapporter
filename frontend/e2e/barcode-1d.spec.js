import {test,expect} from '@playwright/test';
import {nativeScannerPlan} from '../src/barcode-scanner.js';

test('keeps JS fallback when native BarcodeDetector only supports QR',()=>{
 const plan=nativeScannerPlan(['qr_code']);
 expect(plan.accepted).toEqual(['qr_code']);
 expect(plan.oneDimensionalComplete).toBe(false);
 expect(plan.useFallback).toBe(true);
});

test('recognizes native EAN-13, EAN-8 and Code 128 coverage',()=>{
 const plan=nativeScannerPlan(['qr_code','ean_13','ean_8','code_128','upc_a']);
 expect(plan.accepted).toContain('ean_13');
 expect(plan.accepted).toContain('ean_8');
 expect(plan.accepted).toContain('code_128');
 expect(plan.oneDimensionalComplete).toBe(true);
 expect(plan.useFallback).toBe(false);
});
