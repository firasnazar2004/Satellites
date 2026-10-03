# Only deterministic R owns numerical inference. Column references are data, never code.
suppressPackageStartupMessages(library(jsonlite))
args <- commandArgs(trailingOnly=TRUE)
request <- fromJSON(args[1], simplifyVector=FALSE)
d <- read.csv(args[2], check.names=FALSE, stringsAsFactors=FALSE,
              na.strings="", colClasses=unlist(request$column_classes))
conf <- 0.95
numeric_col <- function(x) {
  if (!is.numeric(x)) stop("Expected a numeric column")
  if (any(!is.finite(x))) stop("Non-finite numeric values")
  x
}
run_one <- function(spec) {
  cols <- unlist(spec$columns)
  if (!all(cols %in% names(d))) stop("Unknown column")
  a <- d[,cols,drop=FALSE]
  before <- nrow(a)
  keep <- complete.cases(a)
  a <- a[keep,,drop=FALSE]
  n <- nrow(a)
  if (n < 3) stop("At least three complete observations required")
  result <- list(test=spec$test, columns=as.list(cols), n=n,
                 missing_observations=before-n, confidence_level=conf)
  x <- a[[1]]
  if (spec$test == "descriptive") {
    result$summary <- lapply(a, function(z) {
      z <- numeric_col(z)
      se <- sd(z)/sqrt(length(z))
      margin <- qt(.975,length(z)-1)*se
      list(n=length(z), mean=mean(z), sd=sd(z), median=median(z), min=min(z),
           max=max(z), confidence_interval=c(mean(z)-margin,mean(z)+margin))
    })
    return(result)
  }
  y <- a[[2]]
  test <- spec$test
  if (test %in% c("pearson","spearman")) {
    fit <- cor.test(numeric_col(x),numeric_col(y),method=test,exact=FALSE)
    result$effect_size <- list(name=if(test=="pearson") "r" else "rho", value=unname(fit$estimate))
  } else if (test == "chi_square") {
    tab <- table(x,y)
    if (min(dim(tab)) < 2) stop("Chi-square requires at least two levels in each variable")
    fit <- chisq.test(tab,correct=FALSE)
    result$effect_size <- list(name="Cramers_V",value=sqrt(unname(fit$statistic)/(n*(min(dim(tab))-1))))
    result$minimum_expected_cell <- min(fit$expected)
  } else if (test %in% c("paired_t","wilcoxon")) {
    x <- numeric_col(x); y <- numeric_col(y)
    if(test=="paired_t") {
      fit <- t.test(x,y,paired=TRUE)
      result$effect_size <- list(name="Cohen_dz",value=mean(x-y)/sd(x-y))
    } else {
      fit <- wilcox.test(x,y,paired=TRUE,exact=FALSE,conf.int=TRUE)
      delta <- x-y; delta <- delta[delta!=0]; ranks <- rank(abs(delta))
      result$effect_size <- list(name="paired_rank_biserial",value=sum(sign(delta)*ranks)/sum(ranks))
    }
  } else if (test %in% c("independent_t","mann_whitney","anova","kruskal_wallis")) {
    x <- numeric_col(x); g <- factor(y)
    if (nlevels(g)<2) stop("Grouping variable requires at least two groups")
    result$group_levels <- as.list(levels(g))
    if(test %in% c("independent_t","mann_whitney")) {
      if(nlevels(g)!=2) stop("Exactly two groups required")
      xx <- x[g==levels(g)[1]]; yy <- x[g==levels(g)[2]]
      if(min(length(xx),length(yy))<2) stop("Each group requires at least two observations")
      if(test=="independent_t") {
        fit <- t.test(xx,yy)
        pooled <- sqrt(((length(xx)-1)*var(xx)+(length(yy)-1)*var(yy))/(n-2))
        result$effect_size <- list(name="Cohen_d_pooled",value=(mean(xx)-mean(yy))/pooled)
      } else {
        fit <- wilcox.test(xx,yy,exact=FALSE,conf.int=TRUE)
        result$effect_size <- list(name="rank_biserial",value=2*unname(fit$statistic)/(length(xx)*length(yy))-1)
      }
    } else if(test=="anova") {
      fit_a <- aov(x~g); s <- summary(fit_a)[[1]]
      result$statistic <- s[1,"F value"]; result$p_value <- s[1,"Pr(>F)"]
      result$effect_size <- list(name="eta_squared",value=s[1,"Sum Sq"]/sum(s[,"Sum Sq"]))
      return(result)
    } else {
      fit <- kruskal.test(x,g)
      result$effect_size <- list(name="epsilon_squared",value=max(0,(unname(fit$statistic)-nlevels(g)+1)/(n-nlevels(g))))
    }
  } else if(test %in% c("linear_regression","logistic_regression")) {
    # Safe synthetic names avoid evaluating user column names as R expressions.
    labels <- names(a); names(a) <- paste0("v",seq_along(a))
    form <- reformulate(names(a)[-1],response="v1")
    numeric_col(a$v1)
    if(test=="logistic_regression" && !setequal(unique(a$v1),c(0,1))) stop("Logistic outcome must contain both 0 and 1")
    fit <- if(test=="linear_regression") lm(form,a) else glm(form,a,family=binomial())
    if(df.residual(fit)<=0) stop("Regression requires positive residual degrees of freedom")
    if(test=="logistic_regression" && !fit$converged) stop("Logistic model did not converge")
    s <- summary(fit); co <- coef(s)
    if(any(!is.finite(co)) || fit$rank < length(coef(fit))) stop("Rank-deficient or non-finite model")
    critical <- if(test=="linear_regression") qt(.975,df.residual(fit)) else qnorm(.975)
    result$coefficient_labels <- as.list(setNames(labels,names(a)))
    result$coefficients <- lapply(seq_len(nrow(co)),function(i) {
      ci <- co[i,1]+c(-1,1)*critical*co[i,2]
      z <- list(term=rownames(co)[i],estimate=co[i,1],standard_error=co[i,2],
                statistic=co[i,3],p_value=co[i,4],confidence_interval=ci)
      if(test=="logistic_regression") {
        z$odds_ratio <- exp(co[i,1])
        z$odds_ratio_confidence_interval <- exp(ci)
      }
      z
    })
    if(test=="linear_regression") {
      result$effect_size <- list(name="R_squared",value=s$r.squared)
      f <- s$fstatistic; result$p_value <- unname(pf(f[1],f[2],f[3],lower.tail=FALSE))
    } else {
      result$p_value <- pchisq(fit$null.deviance-fit$deviance,fit$df.null-fit$df.residual,lower.tail=FALSE)
      result$effect_size <- list(name="McFadden_pseudo_R_squared",value=1-fit$deviance/fit$null.deviance)
    }
    result$notes <- "Linear coefficient intervals use t quantiles; logistic intervals are Wald intervals. Regression assumptions require review."
    return(result)
  } else stop("Unsupported analysis")
  result$method <- fit$method
  result$statistic <- unname(fit$statistic)
  result$p_value <- fit$p.value
  result$confidence_interval <- if(is.null(fit$conf.int)) NULL else unname(fit$conf.int)
  result$estimate <- if(is.null(fit$estimate)) NULL else as.list(fit$estimate)
  result
}
results <- lapply(request$analyses,function(spec) {
  warnings <- character()
  out <- tryCatch(withCallingHandlers(run_one(spec),warning=function(w) {
    warnings <<- c(warnings,conditionMessage(w)); invokeRestart("muffleWarning")
  }),error=function(e) list(test=spec$test,columns=spec$columns,error=conditionMessage(e)))
  out$warnings <- as.list(warnings)
  out
})
p <- sapply(results,function(z) if(is.null(z$p_value)) NA_real_ else z$p_value)
valid_p <- is.finite(p)
adjusted <- rep(NA_real_,length(p))
# Descriptive summaries and failed tests have no p-value and are not hypotheses.
adjusted[valid_p] <- p.adjust(p[valid_p],method=request$correction)
for(i in seq_along(results)) {
  results[[i]]$adjusted_p_value <- if(is.na(adjusted[i])) NULL else adjusted[i]
  if(!is.null(results[[i]]$coefficients)) {
    cp <- sapply(results[[i]]$coefficients,function(z) z$p_value)
    ca <- p.adjust(cp,method=request$correction)
    for(j in seq_along(cp)) results[[i]]$coefficients[[j]]$adjusted_p_value <- ca[j]
  }
}
write_json(list(engine=R.version.string,correction=request$correction,
                correction_family="Requested tests; coefficients separately within each model",
                results=results),args[3],auto_unbox=TRUE,pretty=TRUE,na="null",digits=15)
