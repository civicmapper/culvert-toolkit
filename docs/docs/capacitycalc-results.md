# Working with Capacity Calculator Results


Esri Arcade:

```javascript
var fs = FeatureSetByName($datastore, "<name of output layer here>")
var max_return_period_normalized = ($feature.max_return_period - MIN(fs, "max_return_period")) / (MAX(fs, "max_return_period") - MIN(fs, "max_return_period"));
var shed_area_sqkm_normalized = ($feature.shed_area_sqkm - MIN(fs, "shed_area_sqkm")) / (MAX(fs, "shed_area_sqkm") - MIN(fs, "shed_area_sqkm"));
return max_return_period_normalized / shed_area_sqkm_normalized;
```