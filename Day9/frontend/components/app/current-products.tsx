'use client';

import React from 'react';
import { motion } from 'motion/react';
import { cn } from '@/lib/utils';

const MotionDiv = motion.create('div');

interface Product {
  id: string;
  name: string;
  description: string;
  price: number;
  currency: string;
  category: string;
  color?: string;
  sizes?: string[];
  stock: number;
}

interface CurrentProductsProps {
  products: Product[];
  className?: string;
}

export function CurrentProducts({ products, className }: CurrentProductsProps) {
  if (!products || products.length === 0) return null;

  return (
    <MotionDiv
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className={cn('pointer-events-auto', className)}
    >
      <div className="bg-background/90 backdrop-blur-md border border-input/50 rounded-lg shadow-lg p-4">
        <h3 className="text-sm font-semibold mb-3 text-foreground">
          Products ({products.length})
        </h3>
        <div className="space-y-2 max-h-[300px] overflow-y-auto">
          {products.slice(0, 5).map((product, index) => (
            <div key={product.id} className="bg-muted/50 border border-input/30 rounded p-3 text-xs">
              <div className="flex justify-between items-start mb-1">
                <span className="font-medium text-foreground">{index + 1}. {product.name}</span>
                <span className="text-primary font-semibold whitespace-nowrap ml-2">₹{product.price}</span>
              </div>
              <p className="text-muted-foreground text-[10px] mb-1">{product.description}</p>
              <div className="flex gap-2 text-[10px] text-muted-foreground">
                {product.color && (<span className="bg-background/50 px-2 py-0.5 rounded">{product.color}</span>)}
                {product.sizes && (<span className="bg-background/50 px-2 py-0.5 rounded">Sizes: {product.sizes.join(', ')}</span>)}
                <span className="bg-background/50 px-2 py-0.5 rounded">Stock: {product.stock}</span>
              </div>
            </div>
          ))}
          {products.length > 5 && (
            <p className="text-[10px] text-muted-foreground text-center py-2">+ {products.length - 5} more products</p>
          )}
        </div>
      </div>
    </MotionDiv>
  );
}

export default CurrentProducts;
