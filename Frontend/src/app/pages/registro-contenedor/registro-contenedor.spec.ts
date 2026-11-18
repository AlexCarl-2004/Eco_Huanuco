import { ComponentFixture, TestBed } from '@angular/core/testing';

import { RegistroContenedor } from './registro-contenedor';

describe('RegistroContenedor', () => {
  let component: RegistroContenedor;
  let fixture: ComponentFixture<RegistroContenedor>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [RegistroContenedor],
    }).compileComponents();

    fixture = TestBed.createComponent(RegistroContenedor);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
