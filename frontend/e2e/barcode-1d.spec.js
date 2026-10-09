import {test,expect} from '@playwright/test';
import {nativeScannerPlan,requiredOneDimensionalNativeFormats} from '../src/barcode-scanner.js';

test('keeps JS fallback when native BarcodeDetector only supports QR',()=>{
 const plan=nativeScannerPlan(['qr_code']);
 expect(plan.accepted).toEqual(['qr_code']);
 expect(plan.oneDimensionalComplete).toBe(false);
 expect(plan.useFallback).toBe(true);
});

test('keeps JS fallback when native detector is missing any supported 1D symbology',()=>{
 const almostComplete=['qr_code',...requiredOneDimensionalNativeFormats.filter(format=>format!=='upc_e')];
 const plan=nativeScannerPlan(almostComplete);
 expect(plan.accepted).toContain('ean_13');
 expect(plan.accepted).toContain('upc_a');
 expect(plan.oneDimensionalComplete).toBe(false);
 expect(plan.useFallback).toBe(true);
});

test('uses native-only path when all configured 1D formats are available',()=>{
 const plan=nativeScannerPlan(['qr_code',...requiredOneDimensionalNativeFormats]);
 expect(plan.oneDimensionalComplete).toBe(true);
 expect(plan.useFallback).toBe(false);
});
